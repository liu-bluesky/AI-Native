---
name: 系统MCP · prompts.chat
description: 导入自系统 MCP 服务 prompts.chat，包含 tools 10 / prompts 20 / resources 0。 共 30 项能力（tools 10 / prompts 20 / resources 0）
---

# 系统MCP · prompts.chat

## Summary
共 30 项能力（tools 10 / prompts 20 / resources 0）

## Source
- name: prompts.chat
- url: https://prompts.chat/api/mcp
- source: runtime_probe

## Tools
- search_prompts: Search for AI prompts by keyword. Returns matching prompts with title, description, content, author, category, and tags. Use this to discover prompts for various AI tasks like coding, writing, analysis, and more.
- get_prompt: Get a prompt by ID and optionally fill in its variables. If the prompt contains template variables (like {{variable}}), you will be asked to provide values for them.
- save_prompt: Save a new prompt to your prompts.chat account. Requires API key authentication. Prompts are private by default unless configured otherwise in settings.
- improve_prompt: Transform a basic prompt into a well-structured, comprehensive prompt using AI. Optionally searches for similar prompts for inspiration. Supports different output types (text, image, video, sound) and formats (text, JSON, YAML).
- save_skill: Save a new Agent Skill to your prompts.chat account. Skills are multi-file prompts that can include SKILL.md (required), reference docs, scripts, and configuration files. Requires API key authentication. If the file contents are too long, f
- add_file_to_skill: Add a new file to an existing Agent Skill. Use this to add reference docs, scripts, or configuration files to a skill you own.
- update_skill_file: Update an existing file in an Agent Skill. Use this to modify reference docs, scripts, configuration files, or SKILL.md content.
- remove_file_from_skill: Remove a file from an existing Agent Skill. Cannot remove SKILL.md as it is required.
- get_skill: Get an Agent Skill by ID, including all its files (SKILL.md, reference docs, scripts, etc.). Returns the skill metadata and file contents. Save to .claude/skills/{slug}/SKILL.md and .claude/skills/{slug}/[other files] structure if user asks
- search_skills: Search for Agent Skills by keyword. Returns matching skills with title, description, author, and file list. Use this to discover reusable AI agent capabilities for coding, analysis, automation, and more.

## Prompts
- review-the-social-media-content: Review the social media content
- neon-logo-design-for-streaming-platform: Create a circular neon logo with a minimalist play button inside a film strip frame. The design features an electric blue and hot pink gradient glow on a dark background, embodying a cyberpunk aesthetic. It's a centered geometric icon in a 
- extract-a-writing-outline-from-scientific-content: Generate a detailed writing outline based on the principles and concepts described in complex scientific texts.
- resume-customization-prompt-strategic-integrity: Customize your resume for each job, using a number of advanced AI logic elements.
- project-builder: Project Builder
- video-extractor-prompt: Video extractor prompt
- video-review-and-teacher: Video review and teacher
- ai-voice-assistant: This prompt is designed for an AI receptionist (e.g., via Vapi, Bland AI, or a website chatbot) for **your website**.

It focuses on their core value proposition: **Rigorous, reproducible, and non-negotiable analytical quality.**
- build-an-interview-practice-app: Build an AI-powered Interview Preparation app as a single-page website using Streamlit (Python) or Next.js (JavaScript) in VS Code or Cursor. Integrate the OpenAI API, create a system prompt, and design prompts for interview preparation. Th
- deep-investigation-agent: Agente de investigaÃ§Ã£o profunda para pesquisas complexas, sÃ­ntese de informaÃ§Ãµes, anÃ¡lise geopolÃ­tica e contextos acadÃªmicos. Cobre investigaÃ§Ãµes multi-hop, anÃ¡lise de vÃ­deos do YouTube sobre geopolÃ­tica, pesquisa com mÃºltipla
- academic-research-writer: Skill completa para escrita e pesquisa acadÃªmica. Cobre todo o ciclo de vida de um trabalho acadÃªmico: planejamento, pesquisa, revisÃ£o de literatura, redaÃ§Ã£o, anÃ¡lise de dados, formataÃ§Ã£o de citaÃ§Ãµes (APA, MLA, Chicago, Vancouver)
- xcode-mcp-for-pi-agent: Guidelines for efficient Xcode MCP tool usage via mcporter CLI. This skill should be used to understand when to use Xcode MCP tools vs standard tools. Xcode MCP consumes many tokens - use only for build, test, simulator, preview, and Source
- class-prep: I want a prompt that can help be prepare my understanding and get comfortable with the learning input before class starting.
- isc-class-12th-exam-paper-analyzer-and-evaluator: Analyze ISC Class 12th exam papers to generate infographics, scan for previous papers, and provide a personalized strategy.
- code-generation-for-online-assessments: SOLVE THE QUESTION IN CPP, USING NAMESPACE STD, IN A SIMPLE BUT HIGHLY EFFICIENT WAY, AND PROVIDE IT WITH THIS RESTYLING:
no comments, no space between operator and operand but proper margin and indentation, brackets open on the next line a
- photo-enhancement-and-repair-with-transparent-background: upscale this photo and make it look amazing. make it transparent background. fix broken objects. make it good
- improve: Improve
- why-an-online-pdf-editor-is-essential-for-modern-workflows: https://flexfiles.io/en/pdf-editor
- in-depth-paper-and-exam-prediction-analyzer: Analyze supplied exam papers and patterns to predict a comprehensive exam paper for future exams based on in-depth analysis of past papers and questions.
- mine: Mine

## Resources
- none
