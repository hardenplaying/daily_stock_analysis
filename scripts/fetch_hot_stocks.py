# -*- coding: utf-8 -*-
"""自动抓取热门人气股，输出逗号分隔的 A 股代码，供 GitHub Actions 动态生成 STOCK_LIST。

用法：
    python fetch_hot_stocks.py --source eastmoney --top 10

数据源（均为免费、无需 Key）：
    eastmoney      东方财富-个股人气榜（默认，最稳定，返回前 100 只）
    eastmoney_up   东方财富-人气飙升榜（热度上升最快，适合抓异动）

成功时：把逗号分隔的 6 位代码打印到标准输出（stdout），退出码 0。
失败时：错误信息打印到标准错误（stderr），退出码 1，由调用方回退到固定列表。
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import List, Optional

# 6 位 A 股代码正则（沪市 6 开头、深市 0/3 开头，统一按 6 位数字提取）
_CODE_RE = re.compile(r"(\d{6})")


def _extract_codes(frame) -> List[str]:
    """从 DataFrame 中健壮地提取 6 位代码，去重并保持原排名顺序。

    不硬依赖列名：优先使用列名含“代码”的列；若找不到，则在每一列里
    尝试提取 6 位数字，命中比例最高的列作为代码列。
    """
    # 1) 优先按列名定位
    code_col = None
    for col in frame.columns:
        if "代码" in str(col):
            code_col = col
            break

    # 2) 列名定位失败时，按“可提取出 6 位代码的比例”挑选最可靠的列
    if code_col is None:
        best_col, best_ratio = None, 0.0
        for col in frame.columns:
            matched = frame[col].astype(str).str.extract(_CODE_RE)[0].notna().sum()
            ratio = matched / max(len(frame), 1)
            if ratio > best_ratio:
                best_col, best_ratio = col, ratio
        if best_col is None or best_ratio < 0.5:
            raise ValueError("返回数据中找不到可靠的股票代码列")
        code_col = best_col

    # 3) 提取、去重、保序
    codes: List[str] = []
    seen = set()
    for value in frame[code_col].astype(str):
        match = _CODE_RE.search(value)
        if not match:
            continue
        code = match.group(1)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _is_beijing(code: str) -> bool:
    """判断是否为北交所代码（4/8 开头，或 920 号段）。

    沪深 A 股代码只以 6（沪）、0/3（深）开头，因此 4/8/920 开头可安全判定为北交所。
    """
    return code.startswith(("4", "8")) or code.startswith("920")


def fetch_hot(source: str, top: int, include_bj: bool = False) -> List[str]:
    """调用对应数据源，返回前 top 只股票的代码列表。

    include_bj 为 False 时默认排除北交所股票（其数据覆盖与流动性较差）。
    注意：过滤后再截断到 top，保证最终仍能凑够数量。
    """
    import akshare as ak

    source = source.strip().lower()
    if source in ("eastmoney", "em"):
        frame = ak.stock_hot_rank_em()
    elif source in ("eastmoney_up", "em_up"):
        frame = ak.stock_hot_up_em()
    else:
        raise ValueError(f"不支持的数据源: {source}（可选 eastmoney / eastmoney_up）")

    if frame is None or len(frame) == 0:
        raise ValueError("数据源返回为空")

    codes = _extract_codes(frame)
    if not include_bj:
        codes = [c for c in codes if not _is_beijing(c)]
    if not codes:
        raise ValueError("未能从返回数据中解析出任何沪深股票代码")
    return codes[: max(int(top), 1)]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="抓取热门人气股代码")
    parser.add_argument("--source", default="eastmoney",
                        help="数据源：eastmoney（人气榜，默认）或 eastmoney_up（飙升榜）")
    parser.add_argument("--top", type=int, default=10, help="取前 N 只，默认 10")
    parser.add_argument("--include-bj", action="store_true",
                        help="包含北交所股票；默认排除（数据覆盖与流动性较差）")
    args = parser.parse_args(argv)

    try:
        codes = fetch_hot(args.source, args.top, args.include_bj)
    except Exception as exc:  # 任何异常都不允许让整个工作流崩溃
        print(f"[fetch_hot_stocks] 抓取失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # 唯一的标准输出内容：逗号分隔代码，方便 bash 直接捕获
    print(",".join(codes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
