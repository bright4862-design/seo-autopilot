import { readFileSync, existsSync } from "fs";
import { join } from "path";
/**
 * The package that owns an optimizeDeps entry. Deep entries like
 * `react-dom/client` are separate entries to Vite's optimizer but are declared
 * in package.json only under their owning package.
 */
function owningPackage(entry) {
    const segments = entry.split("/");
    return entry.startsWith("@")
        ? segments.slice(0, 2).join("/")
        : segments[0] ?? entry;
}
export function filterPackagesInProject(packages, root) {
    try {
        const packageJsonPath = join(root, "package.json");
        if (!existsSync(packageJsonPath)) {
            return [];
        }
        const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf-8"));
        const allDeps = {
            ...packageJson.dependencies,
            ...packageJson.devDependencies,
            ...packageJson.peerDependencies,
        };
        return packages.filter((pkg) => owningPackage(pkg) in allDeps);
    }
    catch (error) {
        console.warn("Failed to read project package.json:", error);
        return [];
    }
}
//# sourceMappingURL=utils.js.map