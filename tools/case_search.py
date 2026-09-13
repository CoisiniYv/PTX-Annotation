from __future__ import annotations

"""病例列表搜索工具。

特点：
- 支持中文、英文、数字混合关键字。
- 支持 Windows 路径（自动统一大小写、分隔符）。
- 改为精确搜索：只做精确子串匹配，不做模糊相似度匹配。
- 包括文件夹名、文件名、完整路径、basename、stem 的匹配。
- 对日期/编号字符串仍保留数字压缩键，便于输入部分数字搜索。
- 不依赖第三方库，适合直接放入现有项目 tools 目录下使用。
"""

import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

_SPLIT_RE = re.compile(r"[\\/\s._\-]+")
_MULTI_SPACE_RE = re.compile(r"\s+")
_NON_DIGIT_RE = re.compile(r"\D+")


def normalize_search_text(value: object) -> str:
    """将任意输入归一化为适合搜索比较的字符串。"""
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u3000", " ").strip()
    if not text:
        return ""

    # 统一路径分隔符，并尽量规整路径表现
    if "\\" in text or "/" in text:
        try:
            text = os.path.normpath(text)
        except Exception:
            pass
        text = text.replace("\\", "/")

    text = _MULTI_SPACE_RE.sub(" ", text)
    return text.casefold()


def tokenize_search_text(value: object) -> list[str]:
    normalized = normalize_search_text(value)
    if not normalized:
        return []
    return [part for part in _SPLIT_RE.split(normalized) if part]


def digits_only(value: object) -> str:
    normalized = normalize_search_text(value)
    if not normalized:
        return ""
    return _NON_DIGIT_RE.sub("", normalized)


def _path_parts(value: str) -> list[str]:
    """把路径拆成各级目录/文件名段。"""
    if not value:
        return []
    text = value.replace("\\", "/")
    return [part for part in text.split("/") if part]


@dataclass(slots=True)
class SearchMatch:
    matched: bool
    score: float
    matched_text: str = ""


class CaseSearchEngine:
    """病例搜索引擎：精确子串匹配版本。"""

    def __init__(self, query: str | None, fuzzy_threshold: float = 0.58):
        self.raw_query = "" if query is None else str(query)
        self.query = normalize_search_text(self.raw_query)
        self.tokens = tokenize_search_text(self.raw_query)
        self.query_digits = digits_only(self.raw_query)
        self.fuzzy_threshold = fuzzy_threshold  # 保留参数兼容旧调用，但不再使用模糊逻辑

        query_chars = set(self.query)
        numeric_like_chars = set("0123456789 -_./\\")
        self.is_numeric_query = bool(self.query_digits) and query_chars.issubset(numeric_like_chars)

    @property
    def is_empty(self) -> bool:
        return not self.query

    def match(self, candidates: Iterable[object]) -> SearchMatch:
        if self.is_empty:
            return SearchMatch(True, 1.0, "")

        best_score = 0.0
        best_text = ""

        for candidate in candidates:
            raw = "" if candidate is None else str(candidate)
            if not raw:
                continue

            score = self._score_candidate(raw)
            if score > best_score:
                best_score = score
                best_text = raw

            if best_score >= 1.0:
                return SearchMatch(True, best_score, best_text)

        return SearchMatch(best_score > 0.0, best_score, best_text)

    def _score_candidate(self, candidate: str) -> float:
        raw = unicodedata.normalize("NFKC", str(candidate)).strip()
        if not raw:
            return 0.0

        normalized = normalize_search_text(raw)
        if not normalized:
            return 0.0

        posix_path = normalized.replace("\\", "/")
        parts = _path_parts(posix_path)

        basename = os.path.basename(posix_path)
        stem = os.path.splitext(basename)[0]

        normalized_digits = digits_only(normalized)
        basename_digits = digits_only(basename)
        stem_digits = digits_only(stem)
        part_digits = [digits_only(part) for part in parts if digits_only(part)]
        token_digits = [digits_only(tok) for tok in self.tokens if digits_only(tok)]

        # 纯数字查询：仍然精确，但允许数字压缩键命中完整数字串或其子串
        if self.is_numeric_query:
            qd = self.query_digits
            digit_candidates = [stem_digits, basename_digits, normalized_digits, *part_digits, *token_digits]
            digit_candidates = [x for x in digit_candidates if x]

            if not digit_candidates:
                return 0.0

            # 完全相等
            if any(qd == cand for cand in digit_candidates):
                return 1.0

            # 目录名/文件名/完整路径数字串包含
            if any(qd in cand for cand in [stem_digits, basename_digits, normalized_digits] if cand):
                return 0.99

            if any(qd in cand for cand in digit_candidates):
                return 0.97

            return 0.0

        # 非数字查询：只做精确子串匹配，不做模糊
        if self.query == normalized:
            return 1.0

        if self.query == basename or self.query == stem:
            return 0.995

        if self.query in normalized:
            return 0.99

        if self.query in basename or self.query in stem:
            return 0.985

        # 目录名逐段匹配：确保“包括文件夹名”
        if any(self.query == part for part in parts):
            return 0.995

        if any(self.query in part for part in parts):
            return 0.98

        # 分词全命中：例如“张三 CT”同时出现在同一条路径/名称中
        if self.tokens:
            joined = normalized.replace(" ", "")
            if all(token in normalized for token in self.tokens):
                return 0.97
            if all(token in joined for token in self.tokens):
                return 0.965
            if all(any(token in part for part in parts) for token in self.tokens):
                return 0.96

        # 日期/编号型查询的数字压缩键精确匹配
        if self.query_digits and len(self.query_digits) >= 4:
            if self.query_digits == stem_digits or self.query_digits == basename_digits:
                return 0.995
            if self.query_digits in stem_digits or self.query_digits in basename_digits:
                return 0.99
            if self.query_digits in normalized_digits:
                return 0.98

        return 0.0


def build_case_search_candidates(*values: object) -> list[str]:
    """构建用于搜索的候选文本集合。"""
    seen: set[str] = set()
    candidates: list[str] = []

    for value in values:
        if value is None:
            continue

        raw = unicodedata.normalize("NFKC", str(value)).strip()
        if not raw:
            continue

        variants = [raw]

        normalized = normalize_search_text(raw)
        if normalized and normalized != raw:
            variants.append(normalized)

        raw_windows = raw.replace("/", "\\")
        raw_posix = raw.replace("\\", "/")
        if raw_windows != raw:
            variants.append(raw_windows)
        if raw_posix != raw:
            variants.append(raw_posix)

        # 路径的每一段都加入，便于目录名精确命中
        for part in _path_parts(raw_posix):
            variants.append(part)

        basename = os.path.basename(raw_posix)
        stem = os.path.splitext(basename)[0]
        if basename:
            variants.append(basename)
        if stem:
            variants.append(stem)

        # 日期/编号型查询追加数字压缩键
        compact_digits = digits_only(raw)
        if compact_digits:
            variants.append(compact_digits)
            if len(compact_digits) >= 6:
                variants.append(compact_digits[:6])
            if len(compact_digits) >= 8:
                variants.append(compact_digits[:8])

        for token in tokenize_search_text(raw):
            if token:
                variants.append(token)
            td = digits_only(token)
            if td:
                variants.append(td)

        for variant in variants:
            if variant and variant not in seen:
                seen.add(variant)
                candidates.append(variant)

    return candidates