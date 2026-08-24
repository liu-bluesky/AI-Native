#[cfg(windows)]
fn build_attributes() -> tauri_build::Attributes {
    let windows_attributes = tauri_build::WindowsAttributes::new().app_manifest(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>"#,
    );
    tauri_build::Attributes::new().windows_attributes(windows_attributes)
}

#[cfg(not(windows))]
fn build_attributes() -> tauri_build::Attributes {
    tauri_build::Attributes::new()
}

fn main() {
    tauri_build::try_build(build_attributes()).expect("failed to run Tauri build script");
}
