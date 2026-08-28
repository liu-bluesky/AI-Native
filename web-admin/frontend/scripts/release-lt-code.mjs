import { createHash } from 'node:crypto';
import { execFileSync, spawnSync } from 'node:child_process';
import { cp, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectDirectory = path.resolve(scriptDirectory, '..');
const repositoryDirectory = path.resolve(projectDirectory, '..', '..');
const windowsWorkflow = 'package-windows-exe.yml';
const windowsArtifactPrefix = 'lt-code-windows-x64-v';
const macBuilds = [
  { target: 'universal-apple-darwin', directory: 'macOS · 通用' },
  { target: 'aarch64-apple-darwin', directory: 'macOS · Apple 芯片' },
  { target: 'x86_64-apple-darwin', directory: 'macOS · Intel' },
];

function run(command, argumentsList, options = {}) {
  console.log(`\n> ${command} ${argumentsList.join(' ')}`);
  execFileSync(command, argumentsList, { stdio: 'inherit', ...options });
}

function output(command, argumentsList, options = {}) {
  return execFileSync(command, argumentsList, { encoding: 'utf8', ...options }).trim();
}

function releasePlatform() {
  const platformIndex = process.argv.indexOf('--platform');
  const platform = platformIndex === -1 ? 'all' : String(process.argv[platformIndex + 1] || '').trim();

  if (!['all', 'mac', 'windows'].includes(platform)) {
    throw new Error('--platform 仅支持 all、mac 或 windows。');
  }

  return platform;
}

function findGitHubRepository() {
  const remoteUrl = output('git', ['remote', 'get-url', 'origingithub'], { cwd: repositoryDirectory });
  const match = /github\.com[/:]([^/]+)\/([^/.]+)(?:\.git)?$/.exec(remoteUrl);

  if (!match) {
    throw new Error(`无法解析 origingithub 地址：${remoteUrl}`);
  }

  return `${match[1]}/${match[2]}`;
}

function ensureGitHubAuthentication() {
  const result = spawnSync('gh', ['auth', 'status', '--hostname', 'github.com'], { stdio: 'ignore' });

  if (result.error?.code === 'ENOENT') {
    throw new Error('未找到 GitHub CLI。请先安装 gh，然后执行 gh auth login。');
  }

  if (result.status !== 0) {
    throw new Error('GitHub CLI 尚未登录。请先执行 gh auth login，完成登录后再运行打包命令。');
  }
}

function ensureWindowsWorkflowExists(repository) {
  try {
    output('gh', ['workflow', 'view', windowsWorkflow, '--repo', repository], { cwd: repositoryDirectory });
  } catch {
    throw new Error(`GitHub 中未找到 ${windowsWorkflow}。请先提交并推送 .github/workflows/package-windows-exe.yml。`);
  }
}

async function findFiles(directory, suffix) {
  const entries = await readdir(directory, { withFileTypes: true });
  const matches = [];

  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      matches.push(...await findFiles(entryPath, suffix));
    } else if (entry.isFile() && entry.name.endsWith(suffix)) {
      matches.push(entryPath);
    }
  }

  return matches;
}

async function copyBundles(sourceDirectory, suffix, destinationDirectory) {
  const files = await findFiles(sourceDirectory, suffix);
  if (files.length === 0) {
    throw new Error(`未在 ${sourceDirectory} 找到 ${suffix} 安装包。`);
  }

  await mkdir(destinationDirectory, { recursive: true });
  await Promise.all(files.map((filePath) => cp(filePath, path.join(destinationDirectory, path.basename(filePath)))));
}

function startWindowsBuild(repository, branch, version) {
  run('gh', [
    'workflow', 'run', windowsWorkflow,
    '--repo', repository,
    '--ref', branch,
    '--field', `version=${version}`,
  ], { cwd: repositoryDirectory });
}

function getWindowsRunId(repository, version) {
  const expectedTitle = `LT code Windows x64 v${version}`;
  const runs = JSON.parse(output('gh', [
    'run', 'list',
    '--repo', repository,
    '--workflow', windowsWorkflow,
    '--event', 'workflow_dispatch',
    '--limit', '20',
    '--json', 'databaseId,displayTitle',
  ], { cwd: repositoryDirectory }));
  const matchingRun = runs.find((run) => run.displayTitle === expectedTitle);

  return matchingRun?.databaseId;
}

async function waitForWindowsRun(repository, version) {
  for (let retryCount = 0; retryCount < 30; retryCount += 1) {
    const runId = getWindowsRunId(repository, version);
    if (runId) {
      return runId;
    }

    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }

  throw new Error('Windows 构建工作流未在 60 秒内进入 GitHub Actions 队列。');
}

async function writeChecksums(releaseDirectory) {
  const files = (await findFiles(releaseDirectory, '')).filter((filePath) => !filePath.endsWith('SHA256SUMS.txt'));
  const checksums = await Promise.all(files.map(async (filePath) => {
    const hash = createHash('sha256').update(await readFile(filePath)).digest('hex');
    return `${hash}  ${path.relative(releaseDirectory, filePath)}`;
  }));

  await writeFile(path.join(releaseDirectory, 'SHA256SUMS.txt'), `${checksums.sort().join('\n')}\n`);
}

async function buildMacInstallers(releaseDirectory) {
  run('rustup', ['target', 'add', 'aarch64-apple-darwin', 'x86_64-apple-darwin']);
  for (const macBuild of macBuilds) {
    run('npm', ['run', 'tauri:build', '--', '--target', macBuild.target, '--bundles', 'dmg'], { cwd: projectDirectory });
    const bundleDirectory = path.join(projectDirectory, 'src-tauri', 'target', macBuild.target, 'release', 'bundle', 'dmg');
    await copyBundles(bundleDirectory, '.dmg', path.join(releaseDirectory, macBuild.directory));
  }
}

async function buildWindowsInstaller(repository, branch, version, windowsDirectory) {
  startWindowsBuild(repository, branch, version);

  const windowsRunId = await waitForWindowsRun(repository, version);
  run('gh', ['run', 'watch', String(windowsRunId), '--repo', repository, '--exit-status'], { cwd: repositoryDirectory });
  await mkdir(windowsDirectory, { recursive: true });
  run('gh', [
    'run', 'download', String(windowsRunId),
    '--repo', repository,
    '--name', `${windowsArtifactPrefix}${version}`,
    '--dir', windowsDirectory,
  ], { cwd: repositoryDirectory });

  const windowsInstallers = await findFiles(windowsDirectory, '.exe');
  if (windowsInstallers.length === 0) {
    throw new Error('Windows 工作流已完成，但下载结果中没有 .exe 安装包。');
  }
}

async function verifyReleaseVersions(expectedVersion) {
  const versionFiles = [
    ['package-lock.json', JSON.parse(await readFile(path.join(projectDirectory, 'package-lock.json'), 'utf8')).version],
    ['src-tauri/tauri.conf.json', JSON.parse(await readFile(path.join(projectDirectory, 'src-tauri', 'tauri.conf.json'), 'utf8')).version],
  ];
  const cargoManifest = await readFile(path.join(projectDirectory, 'src-tauri', 'Cargo.toml'), 'utf8');
  const cargoVersion = /^version\s*=\s*"([^"]+)"/m.exec(cargoManifest)?.[1];
  versionFiles.push(['src-tauri/Cargo.toml', cargoVersion]);

  const mismatches = versionFiles.filter(([, version]) => version !== expectedVersion);
  if (mismatches.length > 0) {
    const details = mismatches.map(([file, version]) => `${file}: ${version || '未找到'}`).join('，');
    throw new Error(`发布版本不一致，package.json 为 ${expectedVersion}，${details}`);
  }
}

async function main() {
  const platform = releasePlatform();
  const includesMac = platform === 'all' || platform === 'mac';
  const includesWindows = platform === 'all' || platform === 'windows';

  if (includesMac && process.platform !== 'darwin') {
    throw new Error('macOS 安装包只能在 macOS 上构建。');
  }

  const packagePath = path.join(projectDirectory, 'package.json');
  const currentVersion = JSON.parse(await readFile(packagePath, 'utf8')).version;
  const version = currentVersion;
  await verifyReleaseVersions(version);
  const releaseDirectory = path.join(projectDirectory, '发布包', `LT code v${version}`);
  const windowsDirectory = path.join(releaseDirectory, 'Windows · 64 位');

  if (includesMac) {
    await rm(releaseDirectory, { recursive: true, force: true });
    await mkdir(releaseDirectory, { recursive: true });
    await buildMacInstallers(releaseDirectory);
  }

  if (includesWindows) {
    const branch = output('git', ['branch', '--show-current'], { cwd: repositoryDirectory });
    if (!branch) {
      throw new Error('当前仓库处于 detached HEAD，无法触发 Windows 构建。请切换到分支后再执行。');
    }

    const repository = findGitHubRepository();
    ensureGitHubAuthentication();
    ensureWindowsWorkflowExists(repository);
    await buildWindowsInstaller(repository, branch, version, windowsDirectory);
  }

  await mkdir(releaseDirectory, { recursive: true });
  await writeChecksums(releaseDirectory);
  console.log(`\nLT code v${version} ${platform} 安装包已完成：${releaseDirectory}`);
}

main().catch((error) => {
  console.error(`\n打包失败：${error.message}`);
  process.exitCode = 1;
});
