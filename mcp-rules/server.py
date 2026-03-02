"""规则管理 MCP 服务入口"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from store import (
    RuleStore, Rule, ChangelogEntry, SemanticVersion,
    Severity, RiskDomain,
    _serialize_rule, _now_iso,
)

DATA_DIR = Path(__file__).parent / "knowledge"

mcp = FastMCP("rules-service")
rule_store = RuleStore(DATA_DIR)


def _parse_enum(cls, value: str, name: str) -> tuple:
    try:
        return cls(value), None
    except ValueError:
        valid = [e.value for e in cls]
        return None, {"error": f"Invalid {name}: {value}. Valid: {valid}"}


# ── Tools ──

@mcp.tool()
def query_rule(keyword: str, domain: str = "") -> list[dict]:
    """按关键词和领域检索规则"""
    return [_serialize_rule(r) for r in rule_store.query(keyword, domain or None)[:10]]


@mcp.tool()
def get_rule(rule_id: str) -> dict:
    """获取单条规则详情"""
    r = rule_store.get(rule_id)
    if r is None:
        return {"error": f"Rule {rule_id} not found"}
    return _serialize_rule(r)


@mcp.tool()
def submit_rule(
    domain: str, title: str, content: str,
    severity: str = "recommended", risk_domain: str = "low",
) -> dict:
    """提交一条新规则"""
    sev, err = _parse_enum(Severity, severity, "severity")
    if err:
        return err
    rd, err = _parse_enum(RiskDomain, risk_domain, "risk_domain")
    if err:
        return err
    rule = Rule(
        id=rule_store.new_id(), domain=domain,
        title=title, content=content,
        severity=sev, risk_domain=rd,
        version=SemanticVersion(1, 0, 0),
        changelog=(ChangelogEntry(
            version="1.0.0", date=_now_iso(),
            author="user", change="初始创建",
        ),),
    )
    rule_store.save(rule)
    return {"status": "created", "rule_id": rule.id}


@mcp.tool()
def evolve_rule(
    rule_id: str, change_description: str,
    author: str, bump_level: str = "patch",
) -> dict:
    """进化规则：递增版本号并记录变更"""
    rule = rule_store.get(rule_id)
    if rule is None:
        return {"error": f"Rule {rule_id} not found"}
    bumper = {"major": rule.version.bump_major,
              "minor": rule.version.bump_minor,
              "patch": rule.version.bump_patch}
    if bump_level not in bumper:
        return {"error": f"Invalid bump_level: {bump_level}. Valid: {sorted(bumper)}"}
    new_ver = bumper[bump_level]()
    entry = ChangelogEntry(
        version=str(new_ver), date=_now_iso(),
        author=author, change=change_description,
    )
    updated = replace(rule,
                      version=new_ver,
                      changelog=(entry,) + rule.changelog,
                      updated_at=_now_iso())
    rule_store.save(updated)
    return {"status": "evolved", "rule_id": rule_id, "version": str(new_ver)}


@mcp.tool()
def get_rule_stats() -> dict:
    """获取规则库统计信息"""
    all_rules = rule_store.list_all()
    total = len(all_rules)
    if total == 0:
        return {"total": 0, "domains": [], "avg_confidence": 0}
    return {
        "total": total,
        "domains": rule_store.domains(),
        "avg_confidence": round(sum(r.confidence for r in all_rules) / total, 2),
        "verified": sum(1 for r in all_rules if r.confidence >= 0.8),
        "decaying": sum(1 for r in all_rules if r.confidence < 0.3),
    }


@mcp.tool()
def record_feedback(
    rule_id: str, adopted: bool,
) -> dict:
    """记录规则使用反馈（采纳/拒绝），自动更新置信度"""
    r = rule_store.get(rule_id)
    if r is None:
        return {"error": f"Rule {rule_id} not found"}
    rule_store.record_usage(rule_id, adopted)
    updated = rule_store.get(rule_id)
    return {"status": "recorded", "rule_id": rule_id,
            "confidence": updated.confidence, "use_count": updated.use_count}


# ── Resources ──

@mcp.resource("rules://catalog")
def rules_catalog() -> str:
    """所有规则的摘要目录"""
    entries = rule_store.list_all()
    lines = [f"[{e.id}] ({e.domain}) {e.title} | conf={e.confidence}" for e in entries]
    return "\n".join(lines) if lines else "规则库为空"


@mcp.resource("rules://domains")
def rule_domains() -> str:
    """可用的规则领域列表"""
    domains = rule_store.domains()
    return "\n".join(domains) if domains else "暂无领域"


@mcp.resource("rules://{rule_id}")
def rule_detail(rule_id: str) -> str:
    """单条规则详情"""
    r = rule_store.get(rule_id)
    if r is None:
        return f"Rule {rule_id} not found"
    return (
        f"[{r.id}] {r.title}\n"
        f"domain={r.domain} severity={r.severity.value} risk={r.risk_domain.value}\n"
        f"version={r.version} confidence={r.confidence}\n"
        f"content: {r.content}"
    )


# ── Entry Point ──

if __name__ == "__main__":
    mcp.run()
