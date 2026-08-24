#[cfg(windows)]
fn build_attributes() -> tauri_build::Attributes {
    let execution_level = if std::env::var("PROFILE").as_deref() == Ok("release") {
        "requireAdministrator"
    } else {
        "asInvoker"
    };
    let manifest = format!(
        r#"<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <dependency>
    <dependentAssembly>
      <assemblyIdentity
        type="win32"
        name="Microsoft.Windows.Common-Controls"
        version="6.0.0.0"
        processorArchitecture="*"
        publicKeyToken="6595b64144ccf1df"
        language="*"
      />
    </dependentAssembly>
  </dependency>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="{execution_level}" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>"#
    );
    let windows_attributes = tauri_build::WindowsAttributes::new().app_manifest(manifest);
    tauri_build::Attributes::new().windows_attributes(windows_attributes)
}

#[cfg(not(windows))]
fn build_attributes() -> tauri_build::Attributes {
    tauri_build::Attributes::new()
}

fn main() {
    tauri_build::try_build(build_attributes()).expect("failed to run Tauri build script");
}
