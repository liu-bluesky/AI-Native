import assert from "node:assert/strict";
import {
  mergeLocalProjectSources,
  pickDeploySettings,
} from "../src/services/local-project-repository.js";

const boundSettings = {
  version: "2",
  enabled: true,
  default_profile: "prod",
  profiles: [
    {
      id: "prod",
      name: "生产环境",
      components: [
        {
          id: "app",
          name: "默认服务",
          targets: [
            {
              id: "primary",
              ftp_credential_id: "ftp-1",
              remote_path: "/www/site",
              deploy_command: "./deploy.sh",
            },
          ],
        },
      ],
    },
  ],
};

const emptyProfiles = {
  version: "2",
  enabled: false,
  default_profile: "prod",
  profiles: [],
};

const unboundProfiles = {
  version: "2",
  enabled: true,
  default_profile: "prod",
  profiles: [
    {
      id: "prod",
      components: [
        {
          id: "app",
          targets: [{ id: "primary", ftp_credential_id: "", remote_path: "" }],
        },
      ],
    },
  ],
};

const pickedFromEmptyRelations = pickDeploySettings(emptyProfiles, boundSettings);
assert.equal(pickedFromEmptyRelations.profiles[0].components[0].targets[0].ftp_credential_id, "ftp-1");
assert.equal(pickedFromEmptyRelations.profiles[0].components[0].targets[0].remote_path, "/www/site");
assert.equal(pickedFromEmptyRelations.profiles[0].components[0].targets[0].deploy_command, "./deploy.sh");

const pickedFromUnboundRelations = pickDeploySettings(unboundProfiles, boundSettings);
assert.equal(pickedFromUnboundRelations.profiles[0].components[0].targets[0].ftp_credential_id, "ftp-1");
assert.equal(pickedFromUnboundRelations.profiles[0].components[0].targets[0].remote_path, "/www/site");
assert.equal(pickedFromUnboundRelations.profiles[0].components[0].targets[0].deploy_command, "./deploy.sh");

const pickedIncomingBound = pickDeploySettings(boundSettings, emptyProfiles);
assert.equal(pickedIncomingBound.profiles[0].components[0].targets[0].ftp_credential_id, "ftp-1");

const merged = mergeLocalProjectSources(
  [
    {
      id: "project-1",
      name: "站点",
      workspace_path: "/tmp/site",
      deploy_settings: boundSettings,
    },
  ],
  [
    {
      id: "project-1",
      deploy_settings: emptyProfiles,
    },
  ],
  [
    {
      id: "project-1",
      name: "离线快照",
      deploy_settings: unboundProfiles,
    },
  ],
);

assert.equal(merged.length, 1);
assert.equal(
  merged[0].deploy_settings.profiles[0].components[0].targets[0].ftp_credential_id,
  "ftp-1",
);
assert.equal(
  merged[0].deploy_settings.profiles[0].components[0].targets[0].remote_path,
  "/www/site",
);
assert.equal(
  merged[0].deploy_settings.profiles[0].components[0].targets[0].deploy_command,
  "./deploy.sh",
);

const offlineOnly = mergeLocalProjectSources(
  [],
  [],
  [
    {
      id: "project-2",
      name: "仅离线",
      workspace_path: "/tmp/offline",
      deploy_settings: boundSettings,
    },
  ],
);
assert.equal(offlineOnly.length, 1);
assert.equal(
  offlineOnly[0].deploy_settings.profiles[0].components[0].targets[0].ftp_credential_id,
  "ftp-1",
);

console.log("local project deploy settings merge check passed.");
