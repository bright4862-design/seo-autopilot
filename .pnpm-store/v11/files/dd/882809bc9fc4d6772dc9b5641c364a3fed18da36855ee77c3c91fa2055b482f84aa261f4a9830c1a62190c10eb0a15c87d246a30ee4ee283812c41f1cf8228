const { base44 } = require('./base44Client.cjs');

module.exports = new Proxy({}, {
  get: (_, prop) => {
    return (...args) => {
      return base44.functions.invoke(prop, ...args);
    }
  }
});