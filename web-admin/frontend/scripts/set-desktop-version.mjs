import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectDirectory = path.resolve(scriptDirectory, '..');

function readOption(optionName) {
  const optionIndex = process.argv.indexOf(optionName);
  return optionIndex === -1 ? undefined : process.argv[optionIndex + 1];
}

function validateVersion(version) {
  if (!/^\d+\.\d+\.\d+$/.test(version)) {
    throw new Error(`版本号必须是 x.y.z 格式，当前值：${version ?? '(未提供)'}`);
  }
}

async function updateJsonVersion(relativePath, version, updatePackageLock = false) {
  const filePath = path.join(projectDirectory, relativePath);
  const contents = JSON.parse(await readFile(filePath, 'utf8'));
  contents.version = version;

  if (updatePackageLock) {
    contents.packages[''].version = version;
  }

  await writeFile(filePath, `${JSON.stringify(contents, null, 2)}\n`);
}

async function updateCargoVersion(version) {
  const cargoPath = path.join(projectDirectory, 'src-tauri', 'Cargo.toml');
  const cargoContents = await readFile(cargoPath, 'utf8');
  const updatedContents = cargoContents.replace(
    /(^\[package\][\s\S]*?^version\s*=\s*)"[^"]+"/m,
    `$1"${version}"`,
  );

  if (updatedContents === cargoContents) {
    throw new Error('未能在 src-tauri/Cargo.toml 中找到包版本号。');
  }

  await writeFile(cargoPath, updatedContents);
}

async function updateCargoLockVersion(version) {
  const lockPath = path.join(projectDirectory, 'src-tauri', 'Cargo.lock');
  const lockContents = await readFile(lockPath, 'utf8');
  const updatedContents = lockContents.replace(
    /(name = "ai-employee-factory-desktop"\nversion = )"[^"]+"/,
    `$1"${version}"`,
  );

  if (updatedContents === lockContents) {
    throw new Error('未能在 src-tauri/Cargo.lock 中找到桌面端版本号。');
  }

  await writeFile(lockPath, updatedContents);
}

export async function setDesktopVersion(version) {
  validateVersion(version);

  await Promise.all([
    updateJsonVersion('package.json', version),
    updateJsonVersion('package-lock.json', version, true),
    updateJsonVersion(path.join('src-tauri', 'tauri.conf.json'), version),
    updateCargoVersion(version),
    updateCargoLockVersion(version),
  ]);
}

const isDirectExecution = process.argv[1] && path.basename(process.argv[1]) === 'set-desktop-version.mjs';

if (isDirectExecution) {
  const version = readOption('--version');

  try {
    await setDesktopVersion(version);
    console.log(`LT code 版本已更新为 ${version}`);
  } catch (error) {
    console.error(`更新版本失败：${error.message}`);
    process.exitCode = 1;
  }
}
