import fs from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(process.cwd(), '../..');
const docsRoot = path.join(repoRoot, 'docs/liuAgent-cli');
const designDoc = path.join(docsRoot, 'design/15-agent-gateway-mcp.md');
const designIndex = path.join(docsRoot, 'design/README.md');
const projectDesign = path.join(docsRoot, 'PROJECT_DESIGN.md');
const tauriReadme = path.join(process.cwd(), 'src-tauri/README.md');

const checks = [
  {
    file: designDoc,
    terms: [
      'Agent Gateway',
      'ProjectChat Adapter',
      'External System Adapter',
      'Desktop Adapter',
      'Unified MCP',
      'RequirementSession',
      'ProjectContextBundle',
      'PromptBundle',
      'ToolManifestBundle',
      'AgentRuntimeSession',
      'AgentInvocation',
      'AgentRuntimeEvent',
      '服务端只保存配置、需求、任务树、记忆和审计摘要',
      '本地工具执行只发生在 Desktop/Tauri/Local Runner',
      '现有统一查询 MCP 语义不变',
    ],
  },
  {
    file: designIndex,
    terms: ['15-agent-gateway-mcp.md', 'AgentGateway', 'RequirementSession', 'ProjectChat Adapter'],
  },
  {
    file: projectDesign,
    terms: ['Agent Gateway', 'Unified MCP RequirementSession', '服务端只保存配置、需求、任务树、记忆和审计摘要'],
  },
  {
    file: tauriReadme,
    terms: ['Agent Gateway', 'RequirementSession', 'ProjectChat Adapter', '不能执行用户本地工具'],
  },
];

const failures = [];

for (const check of checks) {
  if (!fs.existsSync(check.file)) {
    failures.push(`missing file: ${path.relative(repoRoot, check.file)}`);
    continue;
  }

  const content = fs.readFileSync(check.file, 'utf8');
  for (const term of check.terms) {
    if (!content.includes(term)) {
      failures.push(`${path.relative(repoRoot, check.file)} missing term: ${term}`);
    }
  }
}

if (failures.length > 0) {
  console.error('liuAgent gateway design check failed:');
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log('liuAgent gateway design check passed');
