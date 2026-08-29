import assert from "node:assert/strict";
import {
  buildInteractionUserSummary,
  buildStructuredInteractionPrompt,
  chooseInteractionPresentation,
  extractStructuredInteractionCodeBlocks,
  normalizeStructuredInteraction,
} from "../src/modules/project-chat/services/structuredInteractionProtocol.js";

const interaction = normalizeStructuredInteraction({
  structured_interaction: {
    id: "update-agent-1",
    kind: "confirmation",
    operation: "update_agent",
    user_message: "我准备更新一个售前客服智能体。",
    summary: "请确认更新配置",
    data: { name: "售前客服", channels: ["web", "mobile"] },
    fields: [{ name: "name", label: "名称" }],
    presentation_hint: { type: "form", reason: "配置字段较多" },
  },
});

assert.equal(interaction.id, "update-agent-1");
assert.equal(interaction.confirmationRequired, true);
assert.equal(chooseInteractionPresentation(interaction, { channel: "bot" }), "card");
assert.equal(chooseInteractionPresentation(interaction, { channel: "web" }), "form");
assert.match(buildInteractionUserSummary(interaction), /售前客服/);
assert.match(buildStructuredInteractionPrompt(), /structured_interaction/);
assert.equal(
  extractStructuredInteractionCodeBlocks(
    '说明\n```structured-interaction\n{"kind":"clarification","fields":[{"name":"goal"}]}\n```',
  ).length,
  1,
);
assert.equal(normalizeStructuredInteraction({ foo: "bar" }), null);

console.log("structured interaction protocol checks passed");
