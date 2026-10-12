const { base44 } = require('./base44Client.cjs');

module.exports = new Proxy({}, {
  get: (_, entityName) => {
    return new Proxy({}, {
      get: (_, prop) => {
        if (entityName === 'User') {
          if (prop === 'me') {
            return base44.auth.me;
          }
          if (prop === 'loginWithRedirect' || prop === 'login') {
            return base44.auth.loginWithRedirect;
          }
          if (prop === 'logout') {
            return base44.auth.logout;
          }
          if (prop === 'updateMyUserData') {
            return base44.auth.updateMe;
          }
        }
        return base44.entities[entityName][prop];
      }
    });
  }
});
