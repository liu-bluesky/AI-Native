use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LifecycleState {
    Discovered,
    Loaded,
    Enabled,
    Disabled,
    Failed,
    Disposed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LifecycleEvent {
    pub from: Option<LifecycleState>,
    pub to: LifecycleState,
    pub timestamp_ms: u128,
}

#[derive(Debug, Clone)]
pub struct PluginLifecycle {
    state: LifecycleState,
    history: Vec<LifecycleEvent>,
}

impl PluginLifecycle {
    pub fn discovered() -> Self {
        Self {
            state: LifecycleState::Discovered,
            history: Vec::new(),
        }
    }

    pub fn state(&self) -> LifecycleState {
        self.state
    }

    pub fn history(&self) -> &[LifecycleEvent] {
        &self.history
    }

    pub fn transition(&mut self, next: LifecycleState) -> Result<LifecycleEvent, String> {
        if self.state == next {
            return Err(format!("plugin is already in {:?} state", next));
        }
        if !is_valid_transition(self.state, next) {
            return Err(format!(
                "invalid plugin lifecycle transition: {:?} -> {:?}",
                self.state, next
            ));
        }
        let event = LifecycleEvent {
            from: Some(self.state),
            to: next,
            timestamp_ms: now_ms(),
        };
        self.state = next;
        self.history.push(event);
        Ok(event)
    }
}

fn is_valid_transition(from: LifecycleState, to: LifecycleState) -> bool {
    matches!(
        (from, to),
        (LifecycleState::Discovered, LifecycleState::Loaded)
            | (LifecycleState::Loaded, LifecycleState::Enabled)
            | (LifecycleState::Loaded, LifecycleState::Failed)
            | (LifecycleState::Enabled, LifecycleState::Disabled)
            | (LifecycleState::Enabled, LifecycleState::Failed)
            | (LifecycleState::Disabled, LifecycleState::Enabled)
            | (LifecycleState::Disabled, LifecycleState::Disposed)
            | (LifecycleState::Failed, LifecycleState::Loaded)
            | (LifecycleState::Failed, LifecycleState::Disposed)
            | (LifecycleState::Enabled, LifecycleState::Disposed)
            | (LifecycleState::Loaded, LifecycleState::Disposed)
    )
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn follows_load_enable_disable_dispose_flow() {
        let mut lifecycle = PluginLifecycle::discovered();
        lifecycle.transition(LifecycleState::Loaded).unwrap();
        lifecycle.transition(LifecycleState::Enabled).unwrap();
        lifecycle.transition(LifecycleState::Disabled).unwrap();
        lifecycle.transition(LifecycleState::Disposed).unwrap();
        assert_eq!(lifecycle.state(), LifecycleState::Disposed);
        assert_eq!(lifecycle.history().len(), 4);
    }

    #[test]
    fn rejects_invalid_transition() {
        let mut lifecycle = PluginLifecycle::discovered();
        assert!(lifecycle.transition(LifecycleState::Enabled).is_err());
    }
}
