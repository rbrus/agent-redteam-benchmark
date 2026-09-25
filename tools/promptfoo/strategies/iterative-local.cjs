// Local iterative (PAIR-style) jailbreak for promptfoo 0.123.1.
//
// In this release the built-in strategy id "jailbreak" is a deprecated alias that routes to
// "promptfoo:redteam:iterative:meta", and the meta agent refuses to run without promptfoo's
// hosted generation. The classic iterative provider ("promptfoo:redteam:iterative") still
// ships and runs fully locally with redteam.provider as attacker and the configured grader as
// judge, but no strategy id maps to it anymore. This file does what promptfoo's own
// addIterativeJailbreaks(..., "iterative") does (dist/src/strategies-*.cjs), unchanged.
module.exports = {
  id: 'jailbreak-iterative-local',
  action: async (testCases, injectVar, config) =>
    testCases.map((testCase) => {
      const originalText = String(testCase.vars[injectVar]);
      const inputs = testCase.metadata?.pluginConfig?.inputs;
      // Strategy-only keys that must not leak into the provider config.
      const { plugins: _plugins, numTests: _numTests, ...providerConfig } = config || {};
      return {
        ...testCase,
        provider: {
          id: 'promptfoo:redteam:iterative',
          config: { injectVar, ...providerConfig, ...(inputs && { inputs }) },
        },
        assert: testCase.assert?.map((a) => ({
          ...a,
          metric: a.metric ? `${a.metric}/Iterative` : a.metric,
        })),
        metadata: { ...testCase.metadata, strategyId: 'jailbreak', originalText },
      };
    }),
};
