//! Deterministic, scope-aware system prompt assembly for the local agent runtime.

use std::collections::BTreeMap;
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) enum PromptScope {
    Global,
    Project,
    Session,
    Agent,
}

impl PromptScope {
    pub(crate) fn parse(value: Option<&str>) -> Result<Self, PromptAssemblyError> {
        match value.unwrap_or("project").trim() {
            "" | "project" => Ok(Self::Project),
            "global" => Ok(Self::Global),
            "session" => Ok(Self::Session),
            "agent" => Ok(Self::Agent),
            other => Err(PromptAssemblyError::new(format!(
                "unsupported prompt scope: {other}"
            ))),
        }
    }

    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Global => "global",
            Self::Project => "project",
            Self::Session => "session",
            Self::Agent => "agent",
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub(crate) struct PromptScopeContext {
    pub(crate) active_scope: PromptScope,
}

#[derive(Debug, Clone)]
pub(crate) struct PromptSection {
    pub(crate) id: String,
    pub(crate) source: String,
    pub(crate) scope: PromptScope,
    pub(crate) order: i32,
    pub(crate) text: String,
    pub(crate) complete: bool,
    pub(crate) immutable: bool,
    pub(crate) trusted: bool,
}

#[derive(Debug, Clone)]
pub(crate) struct ResolvedPromptSection {
    pub(crate) id: String,
    pub(crate) source: String,
    pub(crate) scope: PromptScope,
    pub(crate) order: i32,
    pub(crate) text: String,
}

#[derive(Debug, Clone)]
pub(crate) struct PromptAssemblyError {
    message: String,
}

impl PromptAssemblyError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for PromptAssemblyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

/// Registry for one request's prompt contributions.
///
/// Contributions with the same id shadow each other by scope. Ordering uses a
/// stable `(order, id)` key so macOS and Windows produce the same prompt.
pub(crate) struct PromptRegistry {
    context: PromptScopeContext,
    sections: Vec<PromptSection>,
}

impl PromptRegistry {
    pub(crate) fn new(context: PromptScopeContext) -> Self {
        Self {
            context,
            sections: Vec::new(),
        }
    }

    pub(crate) fn register(&mut self, section: PromptSection) {
        self.sections.push(section);
    }

    pub(crate) fn assemble(self) -> Result<Vec<ResolvedPromptSection>, PromptAssemblyError> {
        let mut selected = BTreeMap::<String, PromptSection>::new();
        for section in self.sections.into_iter().filter(|section| {
            section.scope <= self.context.active_scope && !section.text.trim().is_empty()
        }) {
            match selected.get(&section.id) {
                Some(current) if current.immutable => continue,
                Some(current) if current.scope > section.scope => continue,
                _ => {
                    selected.insert(section.id.clone(), section);
                }
            }
        }

        let complete_sections = selected
            .values()
            .filter(|section| section.complete)
            .collect::<Vec<_>>();
        if complete_sections.len() > 1 {
            return Err(PromptAssemblyError::new(format!(
                "multiple complete prompt sections are active: {}",
                complete_sections
                    .iter()
                    .map(|section| section.id.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            )));
        }
        if let Some(section) = complete_sections.first() {
            if !section.trusted {
                return Err(PromptAssemblyError::new(format!(
                    "untrusted prompt section \"{}\" cannot set complete",
                    section.id
                )));
            }
        }

        let complete_id = complete_sections.first().map(|section| section.id.clone());
        let mut resolved = selected
            .into_values()
            .filter(|section| {
                complete_id.is_none()
                    || section.immutable
                    || complete_id.as_deref() == Some(section.id.as_str())
            })
            .map(|section| ResolvedPromptSection {
                id: section.id,
                source: section.source,
                scope: section.scope,
                order: section.order,
                text: section.text,
            })
            .collect::<Vec<_>>();
        resolved.sort_by(|left, right| {
            left.order
                .cmp(&right.order)
                .then_with(|| left.id.cmp(&right.id))
        });
        Ok(resolved)
    }
}

/// Returns whether a tool is permitted by an agent allowlist.
/// An empty allowlist means the runtime has not imposed an agent-specific tool
/// restriction and preserves the caller's existing policy.
pub(crate) fn tool_is_allowed(allowlist: &[String], tool_name: &str) -> bool {
    let allowed = allowlist
        .iter()
        .map(|name| name.trim())
        .filter(|name| !name.is_empty())
        .collect::<Vec<_>>();
    allowed.is_empty() || allowed.into_iter().any(|name| name == tool_name.trim())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn section(id: &str, scope: PromptScope, order: i32, text: &str) -> PromptSection {
        PromptSection {
            id: id.to_string(),
            source: id.to_string(),
            scope,
            order,
            text: text.to_string(),
            complete: false,
            immutable: false,
            trusted: false,
        }
    }

    #[test]
    fn nearest_scope_shadows_the_same_section_id() {
        let mut registry = PromptRegistry::new(PromptScopeContext {
            active_scope: PromptScope::Agent,
        });
        registry.register(section(
            "deployment:persona",
            PromptScope::Global,
            0,
            "global",
        ));
        registry.register(section(
            "deployment:persona",
            PromptScope::Project,
            0,
            "project",
        ));
        registry.register(section(
            "deployment:persona",
            PromptScope::Agent,
            0,
            "agent",
        ));

        let assembled = registry.assemble().unwrap();
        assert_eq!(assembled.len(), 1);
        assert_eq!(assembled[0].text, "agent");
        assert_eq!(assembled[0].scope, PromptScope::Agent);
    }

    #[test]
    fn ordering_is_deterministic_after_scope_resolution() {
        let mut registry = PromptRegistry::new(PromptScopeContext {
            active_scope: PromptScope::Project,
        });
        registry.register(section("tool:z", PromptScope::Global, 100, "z"));
        registry.register(section("persona", PromptScope::Global, 0, "persona"));
        registry.register(section("tool:a", PromptScope::Global, 100, "a"));

        let ids = registry
            .assemble()
            .unwrap()
            .into_iter()
            .map(|section| section.id)
            .collect::<Vec<_>>();
        assert_eq!(ids, ["persona", "tool:a", "tool:z"]);
    }

    #[test]
    fn complete_keeps_immutable_sections_only() {
        let mut registry = PromptRegistry::new(PromptScopeContext {
            active_scope: PromptScope::Project,
        });
        let mut identity = section("harness:identity", PromptScope::Global, -100, "identity");
        identity.immutable = true;
        registry.register(identity);
        let mut complete = section("preset:minimal", PromptScope::Project, 0, "minimal");
        complete.complete = true;
        complete.trusted = true;
        registry.register(complete);
        registry.register(section("tool:file", PromptScope::Global, 100, "tool"));

        let ids = registry
            .assemble()
            .unwrap()
            .into_iter()
            .map(|section| section.id)
            .collect::<Vec<_>>();
        assert_eq!(ids, ["harness:identity", "preset:minimal"]);
    }

    #[test]
    fn tool_allowlist_is_a_strict_opt_in_restriction() {
        let allowlist = vec![" read_file ".to_string(), "search_text".to_string()];
        assert!(tool_is_allowed(&allowlist, "read_file"));
        assert!(tool_is_allowed(&allowlist, "search_text"));
        assert!(!tool_is_allowed(&allowlist, "write_file"));
        assert!(tool_is_allowed(&[], "write_file"));
    }
}
