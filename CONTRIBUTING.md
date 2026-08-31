# 参与 Awesome Quantskills

[English](#english)

感谢你帮助维护这份精选。创建者与维护者：[@abgyjaguo](https://github.com/abgyjaguo)。

## 项目如何进入精选

精选名单不能通过直接修改 README 或数据文件加入。项目必须：

1. 先进入 [Quantskills Registry](https://github.com/quantskills/registry) 的有效资产清单；
2. 完成当前、签名且可验证的 Shadow 评分；
3. Security 为 `pass` 或 `pass_with_warning`；
4. Reliability 等于 100，且没有材料性 Core 回归；
5. 在相同“资产类型 + 一级分类”组内按 Core 排名前 25%。

满足条件后，自动同步会从 Registry 生成更新 PR。这里不接受付费收录、自报分数或手工白名单。

## 可以提交的改进

- 修正展示、翻译、无障碍或文档问题；
- 加强同步器、完整性校验和测试；
- 报告 Registry 与本仓库之间的数据差异。

评分、分类、项目摘要或 Registry 状态有误时，请先在上游 Registry 修复。本仓库不会覆盖权威来源。

## 本地验证

```bash
python -m unittest discover -s tests -v
python scripts/verify.py
python scripts/sync.py --check
```

`sync.py --check` 会访问公开的 GitHub Raw 数据；单元测试和 `verify.py` 不需要网络。

---

<a id="english"></a>

## English

Projects cannot enter this collection through direct README or data edits. They must first be actively listed in the Quantskills Registry, complete the current signed Shadow evaluation, pass the security and reliability gates, have no material Core regression, and rank in the top quartile of the same kind-and-category group.

Contributions may improve presentation, translation, accessibility, synchronization, integrity checks, and tests. Correct scoring, classification, summaries, or Registry status upstream first; this repository never overrides the authoritative source.

