// 在浏览器控制台运行这个脚本来修复字段名问题
(function fixProviderFields() {
    const key = 'local_entities_llm_providers';
    const raw = localStorage.getItem(key);
    if (!raw) {
        console.error('未找到模型供应商数据');
        return;
    }

    const providers = JSON.parse(raw);
    let fixed = 0;

    providers.forEach(provider => {
        // 修复 baseUrl -> base_url
        if (provider.baseUrl && !provider.base_url) {
            provider.base_url = provider.baseUrl;
            delete provider.baseUrl;
            fixed++;
        }
        // 修复 apiKey -> api_key
        if (provider.apiKey && !provider.api_key) {
            provider.api_key = provider.apiKey;
            delete provider.apiKey;
            fixed++;
        }
        // 确保必要字段存在
        if (!provider.base_url) {
            provider.base_url = '';
        }
        if (!provider.model_configs) {
            provider.model_configs = [];
        }
    });

    localStorage.setItem(key, JSON.stringify(providers));
    console.log(`✓ 已修复 ${fixed} 个字段问题，共 ${providers.length} 个供应商`);
    console.table(providers.map(p => ({
        name: p.name,
        base_url: p.base_url || '❌ 仍然缺失',
        enabled: p.enabled !== false
    })));

    // 触发更新事件
    window.dispatchEvent(new CustomEvent('local-entities-updated', {
        detail: { entityName: 'llm_providers', entities: providers }
    }));
})();
