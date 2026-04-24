const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");
const path = require("path");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

// Monorepo: watch the workspace root and resolve from both node_modules
config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];

// Force Metro to always resolve React 19 from apps/mobile/node_modules, not the hoisted
// React 18 in the workspace root. extraNodeModules alone doesn't override tree-walk
// resolution for files inside root node_modules (e.g. expo-router), so we use
// resolveRequest to re-root the lookup for React core packages.
const REACT_PKGS = /^(react|react-dom|react-native)(\/.*)?$/;

config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (REACT_PKGS.test(moduleName)) {
    return context.resolveRequest(
      { ...context, originModulePath: path.resolve(projectRoot, "package.json") },
      moduleName,
      platform
    );
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = withNativeWind(config, { input: "./global.css" });
