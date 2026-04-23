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
- what-friendship-should-be-all-about: What friendship should be all about
- building-a-community: Building a community
- realistic-image-json-prompt: A JSON-based prompt for generating realistic images. This prompt allows users to specify various parameters and constraints to create detailed and lifelike images using AI technologies. It is ideal for artists, designers, and developers loo
- suitable-sunglasses-using-gemini: provide an image and gemini suggest suitable sunglass frames
- key-concepts-and-essential-definitions-for-exam: NotebookLM - Key Concepts and Essential Definitions for Exam
- chain-of-thought-for-podcast-guest-analysis: This prompt guides you through a structured process to gather detailed information about your podcast guest and develop probing questions that may challenge them, ideally suited for the "Shadow Work" podcast.
- augmented-reality-real-estate-staging: Use augmented reality to virtually stage real estate properties using user-provided images of staging inventory.
- good-for-us: Good for us
- rocket-launcher: Rocket launcher
- create-a-can-simulation-in-python: create a a CAN simulation so when i run it i undertsand how CAN works crteate it in python
- grant-finder: This prompt helps users find grants relevant to their needs by acting as a research assistant that identifies and suggests potential grant opportunities based on user criteria.
- promptforge: PromptForge âï¸ is an advanced prompt optimization system designed to systematically analyze your prompts, identify weaknesses, and transform them into clearer, more precise, and more reliable versions.

It goes beyond surface-level sugg
- school-report-management-system-for-smp-negeri-7-sentani: Develop an application for SMP Negeri 7 Sentani where the Principal acts as the Master Admin and Class Teachers as Admins. The application manages school reports based on Kurikulum 2013, Kurikulum Merdeka, and Kurikulum Deep Learning. Key f
- ee: âI want you to analyze the videos and images I upload and recreate the exact same style.
Give me outputs like example voice, dialogue delivery, video style, dialogue delivery format, 4K aspect ratio exatra exatra, and all other stylistic 
- financial-compliance-auditor: Review and ensure compliance of financial reports with capital markets regulations, focusing on neutrality, risk assessment, and legal completeness, outputting the final document in Turkish.
- feynmans-nitpick-game: Feynmanâs Nitpicking" to convey the core idea
- create-content-from-discord-blog-for-hazels-website: Generate site-specific content based on the Discord blog, tailored for Hazel's website.
- lecturer: Act like uniksun lecturer
- github-ssh-setup-for-students-existing-repository-clone-push-ready: Guide for students to configure GitHub SSH access, ensuring they can clone and push to an existing repository securely without needing GitHub passwords or tokens. Follow step-by-step instructions to verify SSH key setup and repository readi
- setup-and-bootstrap-a-flutter-development-environment: Guide for setting up a comprehensive Flutter development environment and bootstrapping a production-ready Flutter project. Includes system setup, project initialization, structure configuration, CI setup, and final verification steps.

## Resources
- none
