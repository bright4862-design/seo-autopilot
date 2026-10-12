const { base44 } = require("./base44Client.cjs");

module.exports = new Proxy(
  {},
  {
    get: (_, prop) => {
      if (prop === "agentSDK" || prop === "default") {
        return base44.agents;
      }
      return base44.agents[prop];
    },
  }
);
