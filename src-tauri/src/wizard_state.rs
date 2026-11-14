use std::sync::atomic::{AtomicBool, Ordering};

/// Tracks whether the desktop shell is currently presenting the First-Time Setup Wizard
/// instead of the bottom-right mini-tray flyout.
#[derive(Debug, Default)]
pub struct WizardWindowState {
    wizard_active: AtomicBool,
}

impl WizardWindowState {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_active(&self) -> bool {
        self.wizard_active.load(Ordering::SeqCst)
    }

    pub fn set_active(&self, active: bool) {
        self.wizard_active.store(active, Ordering::SeqCst);
    }
}

/// Decides whether the setup wizard should open automatically on app startup.
///
/// Legacy Beta upgrades that already have a valid configured server + credential profile
/// skip the wizard even if `first_run_setup` was absent or stale (`true`).
pub fn should_open_wizard_on_startup(
    explicit_flag: Option<bool>,
    has_valid_server_and_creds: bool,
) -> bool {
    if has_valid_server_and_creds {
        return false;
    }
    explicit_flag.unwrap_or(true)
}

/// Clamps incoming wizard window dimensions to safe logical bounds (`460..=540` x `480..=760`).
pub fn clamp_wizard_dimensions(width: Option<f64>, height: Option<f64>) -> (f64, f64) {
    let w = width
        .filter(|v| v.is_finite())
        .unwrap_or(460.0)
        .clamp(460.0, 540.0);
    let h = height
        .filter(|v| v.is_finite())
        .unwrap_or(560.0)
        .clamp(480.0, 760.0);
    (w, h)
}

/// Returns `true` when `myserver:reset-home` and taskbar snap events must be suppressed
/// so tray/focus events do not reset wizard state or pull the centered wizard to the taskbar.
pub fn should_suppress_home_reset(wizard_active: bool) -> bool {
    wizard_active
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean_default_startup_opens_wizard() {
        assert!(should_open_wizard_on_startup(None, false));
        assert!(should_open_wizard_on_startup(Some(true), false));
        assert!(!should_open_wizard_on_startup(Some(false), false));
    }

    #[test]
    fn legacy_upgrade_with_valid_creds_skips_wizard() {
        assert!(!should_open_wizard_on_startup(None, true));
    }

    #[test]
    fn stale_first_run_flag_with_valid_creds_skips_wizard() {
        assert!(!should_open_wizard_on_startup(Some(true), true));
        assert!(!should_open_wizard_on_startup(Some(false), true));
    }

    #[test]
    fn clamp_wizard_dimensions_handles_defaults_and_bounds() {
        assert_eq!(clamp_wizard_dimensions(None, None), (460.0, 560.0));
        assert_eq!(
            clamp_wizard_dimensions(Some(540.0), Some(640.0)),
            (540.0, 640.0)
        );
        assert_eq!(
            clamp_wizard_dimensions(Some(120.0), Some(200.0)),
            (460.0, 480.0)
        );
        assert_eq!(
            clamp_wizard_dimensions(Some(1200.0), Some(2400.0)),
            (540.0, 760.0)
        );
        assert_eq!(
            clamp_wizard_dimensions(Some(f64::NAN), Some(f64::INFINITY)),
            (460.0, 560.0)
        );
    }

    #[test]
    fn wizard_window_state_toggles_and_suppresses_home_reset() {
        let state = WizardWindowState::new();
        assert!(!state.is_active());
        assert!(!should_suppress_home_reset(state.is_active()));

        state.set_active(true);
        assert!(state.is_active());
        assert!(should_suppress_home_reset(state.is_active()));

        state.set_active(false);
        assert!(!state.is_active());
        assert!(!should_suppress_home_reset(state.is_active()));
    }
}
