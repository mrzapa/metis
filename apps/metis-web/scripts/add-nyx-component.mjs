import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const scriptDir = path.dirname(scriptPath);
const require = createRequire(import.meta.url);
export const appRoot = path.resolve(scriptDir, "..");
const packageJsonPath = path.join(appRoot, "package.json");
const nyxSnapshotPath = path.resolve(appRoot, "..", "..", "metis_app", "assets", "nyx_catalog_snapshot.json");
const nyxRegistryBaseUrl = "https://nyxui.com/r/";
const WINDOWS_ABSOLUTE_TARGET_PATTERN = /^[A-Za-z]:[\\/]/;

export const SHADCN_REGISTRY_NAME = "@shadcn";
export const NYX_REGISTRY_NAME = "@nyx";
export const NYX_REGISTRY_URL_TEMPLATE = "https://nyxui.com/r/{name}.json";
export const DEFAULT_NYX_VALIDATION_COMPONENT = "glow-card";
export const NYX_CATALOG_SNAPSHOT = require(nyxSnapshotPath);
const DEFAULT_NYX_INSTALL_TARGET_POLICY = Object.freeze({
  allowedTargetPrefixes: Object.freeze(["components/", "hooks/", "lib/"]),
  allowedTargetlessTypes: Object.freeze(["registry:lib"]),
  policyName: "metis_nyx_targets_v1",
});

function dedupeStrings(values) {
  if (!Array.isArray(values)) {
    return [];
  }

  const deduped = [];
  const seen = new Set();
  for (const rawValue of values) {
    if (typeof rawValue !== "string") {
      continue;
    }

    const normalized = rawValue.trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }

    seen.add(normalized);
    deduped.push(normalized);
  }

  return deduped;
}

function coerceBoolean(value, fallback) {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "number") {
    return value !== 0;
  }

  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (["true", "1", "yes", "y", "on"].includes(normalized)) {
      return true;
    }
    if (["false", "0", "no", "n", "off"].includes(normalized)) {
      return false;
    }
  }

  return fallback;
}

function toComponentDescription(component) {
  if (isNonEmptyString(component.curated_description)) {
    return component.curated_description.trim();
  }
  if (isNonEmptyString(component.description)) {
    return component.description.trim();
  }
  return "";
}

function toNyxInstallTargetPolicy(snapshot) {
  const targetPolicy = isPlainObject(snapshot?.install_target_policy)
    ? snapshot.install_target_policy
    : {};
  const allowedTargetPrefixes = dedupeStrings(targetPolicy.allowed_target_prefixes);
  const allowedTargetlessTypes = dedupeStrings(targetPolicy.allowed_targetless_types);

  return {
    allowedTargetPrefixes:
      allowedTargetPrefixes.length > 0
        ? allowedTargetPrefixes
        : [...DEFAULT_NYX_INSTALL_TARGET_POLICY.allowedTargetPrefixes],
    allowedTargetlessTypes:
      allowedTargetlessTypes.length > 0
        ? allowedTargetlessTypes
        : [...DEFAULT_NYX_INSTALL_TARGET_POLICY.allowedTargetlessTypes],
    policyName: isNonEmptyString(targetPolicy.policy_name)
      ? targetPolicy.policy_name.trim()
      : DEFAULT_NYX_INSTALL_TARGET_POLICY.policyName,
  };
}

function buildGovernedNyxComponentMaps(snapshot) {
  if (!isPlainObject(snapshot) || !isPlainObject(snapshot.components)) {
    throw new Error("[ui:add:nyx] Packaged Nyx snapshot must expose a components object.");
  }

  const installableComponents = {};
  const previewableComponents = {};

  for (const [rawComponentName, rawComponent] of Object.entries(snapshot.components)) {
    if (!isPlainObject(rawComponent)) {
      continue;
    }

    const componentName = normalizeNyxSpecifier(rawComponent.component_name ?? rawComponentName);
    if (!componentName) {
      continue;
    }

    const reviewStatus = isNonEmptyString(rawComponent.review_status)
      ? rawComponent.review_status.trim().toLowerCase()
      : "installable";
    const installPathIssues = dedupeStrings(rawComponent.install_path_issues);
    const auditIssues = dedupeStrings(rawComponent.audit_issues);
    const installPathSafe = coerceBoolean(rawComponent.install_path_safe, true);
    const installable = coerceBoolean(
      rawComponent.installable,
      reviewStatus === "installable" && installPathSafe && auditIssues.length === 0 && installPathIssues.length === 0,
    );
    const previewable = coerceBoolean(rawComponent.previewable, true);

    const governedComponent = {
      auditIssues,
      description: toComponentDescription(rawComponent),
      installPathIssues,
      installPathSafe,
      installable,
      previewable,
      requiredDependencies: dedupeStrings(
        rawComponent.required_dependencies ?? rawComponent.requiredDependencies,
      ),
      reviewStatus,
    };

    if (previewable) {
      previewableComponents[componentName] = governedComponent;
    }

    if (installable && installPathSafe) {
      installableComponents[componentName] = governedComponent;
    }
  }

  return {
    installableComponents,
    previewableComponents,
  };
}

const { installableComponents, previewableComponents } = buildGovernedNyxComponentMaps(NYX_CATALOG_SNAPSHOT);
export const NYX_INSTALL_TARGET_POLICY = toNyxInstallTargetPolicy(NYX_CATALOG_SNAPSHOT);

export const CURATED_NYX_COMPONENTS = installableComponents;
export const PREVIEWABLE_NYX_COMPONENTS = previewableComponents;

const curatedComponentNames = Object.keys(CURATED_NYX_COMPONENTS).sort();

function hasOwnComponent(name) {
  return Object.prototype.hasOwnProperty.call(CURATED_NYX_COMPONENTS, name);
}

function toNyxTarget(componentName) {
  return `${NYX_REGISTRY_NAME}/${componentName}`;
}

function coerceRegistryUrl(registry) {
  return typeof registry === "string" ? registry : registry?.url;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isPackageDependencySpecifier(value) {
  if (typeof value !== "string") {
    return false;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }

  if (trimmed.startsWith(".") || trimmed.startsWith("/") || trimmed.includes("\\") || /\s/.test(trimmed)) {
    return false;
  }

  return /^(?:@[A-Za-z0-9._-]+\/)?[A-Za-z0-9._-]+$/.test(trimmed);
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function normalizeRegistryFiles(rawFiles) {
  if (!Array.isArray(rawFiles)) {
    return [];
  }

  const files = [];
  for (const rawFile of rawFiles) {
    if (!isPlainObject(rawFile)) {
      continue;
    }

    const filePath = isNonEmptyString(rawFile.path) ? rawFile.path.trim() : "";
    const fileType = isNonEmptyString(rawFile.file_type)
      ? rawFile.file_type.trim()
      : isNonEmptyString(rawFile.type)
        ? rawFile.type.trim()
        : "registry:file";
    const target = isNonEmptyString(rawFile.target) ? rawFile.target.trim() : "";

    if (!filePath && !target) {
      continue;
    }

    files.push({
      filePath,
      fileType,
      target,
    });
  }

  return files;
}

export function normalizeNyxSpecifier(specifier) {
  if (typeof specifier !== "string") {
    return undefined;
  }

  const trimmed = specifier.trim();
  if (!trimmed) {
    return undefined;
  }

  if (trimmed.startsWith(nyxRegistryBaseUrl)) {
    const [resourceName] = trimmed.slice(nyxRegistryBaseUrl.length).split("?");
    return resourceName.endsWith(".json") ? resourceName.slice(0, -5) : resourceName;
  }

  if (trimmed.startsWith("@nyx/")) {
    return trimmed.slice("@nyx/".length);
  }

  if (trimmed.startsWith("nyx/")) {
    return trimmed.slice("nyx/".length);
  }

  return trimmed;
}

export function auditNyxInstallTargets(
  componentName,
  registryItem,
  targetPolicy = NYX_INSTALL_TARGET_POLICY,
) {
  const issues = [];

  for (const fileSummary of normalizeRegistryFiles(registryItem?.files)) {
    const target = fileSummary.target;
    const fileType = fileSummary.fileType;
    const sourcePath = fileSummary.filePath || "<unknown>";

    if (!target) {
      if (targetPolicy.allowedTargetlessTypes.includes(fileType)) {
        continue;
      }

      issues.push(
        `${componentName}: ${sourcePath} has no install target for file type ${fileType}`,
      );
      continue;
    }

    const normalizedTarget = target.replace(/\\/g, "/");

    if (normalizedTarget.startsWith("/") || WINDOWS_ABSOLUTE_TARGET_PATTERN.test(target)) {
      issues.push(`${componentName}: ${target} must remain relative to the app root`);
      continue;
    }

    if (target.includes("\\")) {
      issues.push(`${componentName}: ${target} must use POSIX path separators`);
      continue;
    }

    if (normalizedTarget.split("/").includes("..")) {
      issues.push(`${componentName}: ${target} cannot traverse parent directories`);
      continue;
    }

    if (!targetPolicy.allowedTargetPrefixes.some((prefix) => normalizedTarget.startsWith(prefix))) {
      issues.push(
        `${componentName}: ${target} is outside the allowed target prefixes ${targetPolicy.allowedTargetPrefixes.join(", ")}`,
      );
    }
  }

  return issues;
}

export function resolveNyxComponents(specifiers) {
  const selected = [];
  const rejected = [];
  const seen = new Set();

  for (const specifier of specifiers) {
    const normalized = normalizeNyxSpecifier(specifier);
    if (!normalized) {
      continue;
    }

    if (!hasOwnComponent(normalized)) {
      rejected.push(normalized);
      continue;
    }

    if (seen.has(normalized)) {
      continue;
    }

    seen.add(normalized);
    selected.push(normalized);
  }

  return {
    rejected,
    selected,
  };
}

export function findMissingDependencies(componentNames, packageManifest) {
  const declaredDependencies = new Set([
    ...Object.keys(packageManifest.dependencies ?? {}),
    ...Object.keys(packageManifest.devDependencies ?? {}),
  ]);
  const missingDependencies = new Set();

  for (const componentName of componentNames) {
    if (!hasOwnComponent(componentName)) {
      continue;
    }

    for (const dependencyName of CURATED_NYX_COMPONENTS[componentName].requiredDependencies) {
      if (!declaredDependencies.has(dependencyName)) {
        missingDependencies.add(dependencyName);
      }
    }
  }

  return [...missingDependencies].sort();
}

export function formatCuratedNyxList() {
  return curatedComponentNames
    .map((componentName) => {
      const component = CURATED_NYX_COMPONENTS[componentName];
      const dependencyLabel =
        component.requiredDependencies.length > 0
          ? component.requiredDependencies.join(", ")
          : "none";

      return `- ${componentName}: ${component.description} deps: ${dependencyLabel}`;
    })
    .join("\n");
}

export function auditNyxRegistryItem(componentName, registryItem) {
  const issues = [];

  if (!registryItem || typeof registryItem !== "object") {
    return [`${componentName}: registry item could not be loaded`];
  }

  if (registryItem.name !== componentName) {
    issues.push(
      `${componentName}: registry item name mismatch (${registryItem.name ?? "missing name"})`,
    );
  }

  if (!Array.isArray(registryItem.files) || registryItem.files.length === 0) {
    issues.push(`${componentName}: registry item does not declare any files`);
  }

  for (const fieldName of ["dependencies", "devDependencies"]) {
    const fieldValue = registryItem[fieldName];

    if (fieldValue === undefined || fieldValue === null) {
      continue;
    }

    if (!Array.isArray(fieldValue)) {
      issues.push(`${componentName}: ${fieldName} must be an array when present`);
      continue;
    }

    const invalidSpecifiers = fieldValue.filter((specifier) => !isPackageDependencySpecifier(specifier));
    if (invalidSpecifiers.length > 0) {
      issues.push(
        `${componentName}: ${fieldName} contains invalid package specifiers: ${invalidSpecifiers.join(", ")}`,
      );
    }
  }

  const registryDependencies = registryItem.registryDependencies;
  if (registryDependencies !== undefined && registryDependencies !== null) {
    if (!Array.isArray(registryDependencies)) {
      issues.push(`${componentName}: registryDependencies must be an array when present`);
    } else {
      const invalidRegistryDependencies = registryDependencies.filter(
        (specifier) => !isNonEmptyString(specifier),
      );

      if (invalidRegistryDependencies.length > 0) {
        issues.push(`${componentName}: registryDependencies contains blank or non-string entries`);
      }
    }
  }

  issues.push(...auditNyxInstallTargets(componentName, registryItem));

  return issues;
}

export async function validateInstalledShadcnConfig(cwd = appRoot) {
  const configPath = path.join(cwd, "components.json");
  const parsedConfig = JSON.parse(await readFile(configPath, "utf8"));

  if (!isPlainObject(parsedConfig)) {
    throw new Error(`[ui:add:nyx] ${configPath} must contain a JSON object.`);
  }

  const registries = parsedConfig.registries ?? {};
  if (!isPlainObject(registries)) {
    throw new Error(`[ui:add:nyx] registries in ${configPath} must be an object when present.`);
  }

  for (const [registryName, registryValue] of Object.entries(registries)) {
    if (!registryName.startsWith("@")) {
      throw new Error(`[ui:add:nyx] Registry names must start with @. Invalid registry: ${registryName}.`);
    }

    if (registryName === SHADCN_REGISTRY_NAME) {
      throw new Error(
        `[ui:add:nyx] ${SHADCN_REGISTRY_NAME} is built in to shadcn and must not be overridden in components.json.`,
      );
    }

    const registryUrl = coerceRegistryUrl(registryValue);
    if (!isNonEmptyString(registryUrl)) {
      throw new Error(`[ui:add:nyx] Registry ${registryName} must declare a non-empty URL.`);
    }

    if (!registryUrl.includes("{name}")) {
      throw new Error(`[ui:add:nyx] Registry ${registryName} URL must include the {name} placeholder.`);
    }
  }

  const nyxRegistry = registries[NYX_REGISTRY_NAME];

  if (!nyxRegistry) {
    throw new Error(`[ui:add:nyx] ${NYX_REGISTRY_NAME} is not configured in components.json.`);
  }

  const nyxRegistryUrl = coerceRegistryUrl(nyxRegistry);
  if (nyxRegistryUrl !== NYX_REGISTRY_URL_TEMPLATE) {
    throw new Error(
      `[ui:add:nyx] ${NYX_REGISTRY_NAME} must point to ${NYX_REGISTRY_URL_TEMPLATE}, found ${nyxRegistryUrl}.`,
    );
  }

  return {
    registries: {
      [SHADCN_REGISTRY_NAME]: "built-in",
      ...registries,
    },
    nyxRegistryUrl,
  };
}

async function fetchNyxRegistryItem(componentName, nyxRegistryUrl = NYX_REGISTRY_URL_TEMPLATE) {
  const registryItemUrl = nyxRegistryUrl.replace("{name}", componentName);
  const response = await fetch(registryItemUrl, {
    headers: {
      accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`failed to fetch ${registryItemUrl} (${response.status} ${response.statusText})`);
  }

  return response.json();
}

export async function auditCuratedNyxComponents(componentNames = curatedComponentNames, nyxRegistryUrl) {
  if (componentNames.length === 0) {
    return {
      invalidComponents: [],
      issuesByComponent: {},
    };
  }

  const resolvedNyxRegistryUrl =
    nyxRegistryUrl ?? (await validateInstalledShadcnConfig()).nyxRegistryUrl;
  const issuesByComponent = {};

  await Promise.all(
    componentNames.map(async (componentName) => {
      let issues;

      try {
        const registryItem = await fetchNyxRegistryItem(componentName, resolvedNyxRegistryUrl);
        issues = auditNyxRegistryItem(componentName, registryItem);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        issues = [`${componentName}: ${message}`];
      }

      if (issues.length > 0) {
        issuesByComponent[componentName] = issues;
      }
    }),
  );

  return {
    invalidComponents: Object.keys(issuesByComponent).sort(),
    issuesByComponent,
  };
}

export function parseCliArgs(args = process.argv.slice(2)) {
  const componentSpecifiers = [];
  const forwardedArgs = [];
  let dryRun = false;
  let list = false;
  let validate = false;

  for (const arg of args) {
    if (arg === "--") {
      continue;
    }

    if (arg === "--list") {
      list = true;
      continue;
    }

    if (arg === "--validate") {
      validate = true;
      continue;
    }

    if (arg === "--dry-run") {
      dryRun = true;
      continue;
    }

    if (arg.startsWith("-")) {
      forwardedArgs.push(arg);
      continue;
    }

    componentSpecifiers.push(arg);
  }

  return {
    componentSpecifiers,
    dryRun,
    forwardedArgs,
    list,
    validate,
  };
}

function formatAuditIssues(issuesByComponent) {
  return Object.entries(issuesByComponent)
    .map(([componentName, issues]) => `- ${componentName}: ${issues.join("; ")}`)
    .join("\n");
}

export function resolveShadcnCliPath(cwd = appRoot) {
  const shadcnModulePath = require.resolve("shadcn", { paths: [cwd] });
  const shadcnPackageJsonPath = path.resolve(path.dirname(shadcnModulePath), "..", "package.json");
  const shadcnPackageJson = require(shadcnPackageJsonPath);
  const binEntry =
    typeof shadcnPackageJson.bin === "string"
      ? shadcnPackageJson.bin
      : shadcnPackageJson.bin?.shadcn;

  if (!isNonEmptyString(binEntry)) {
    throw new Error("[ui:add:nyx] Unable to resolve the installed shadcn CLI entrypoint.");
  }

  return path.resolve(path.dirname(shadcnPackageJsonPath), binEntry);
}

export function buildShadcnCliArgs(operation, targets, forwardedArgs = [], cwd = appRoot) {
  return [resolveShadcnCliPath(cwd), operation, ...forwardedArgs, ...targets];
}

export function runShadcnCommand(operation, targets, forwardedArgs = [], options = {}) {
  const {
    cwd = appRoot,
    spawnImplementation = spawnSync,
    stdio = "inherit",
  } = options;
  const commandResult = spawnImplementation(process.execPath, buildShadcnCliArgs(operation, targets, forwardedArgs, cwd), {
    cwd,
    stdio,
  });

  if (commandResult.error) {
    throw commandResult.error;
  }

  return commandResult.status ?? 1;
}

async function runValidation() {
  const { nyxRegistryUrl } = await validateInstalledShadcnConfig();
  const auditResult = await auditCuratedNyxComponents(curatedComponentNames, nyxRegistryUrl);

  if (auditResult.invalidComponents.length > 0) {
    console.error("[ui:add:nyx] Reviewed Nyx component audit failed:");
    console.error(formatAuditIssues(auditResult.issuesByComponent));
    return 1;
  }

  console.log("[ui:add:nyx] shadcn configuration accepted.");
  console.log("[ui:add:nyx] verifying default shadcn registry access...");
  const defaultViewStatus = runShadcnCommand("view", ["button"]);

  if (defaultViewStatus !== 0) {
    return defaultViewStatus;
  }

  console.log(`[ui:add:nyx] verifying ${NYX_REGISTRY_NAME} registry access...`);
  return runShadcnCommand("view", [toNyxTarget(DEFAULT_NYX_VALIDATION_COMPONENT)]);
}

function printUsage() {
  console.log("Usage: pnpm ui:add:nyx -- <component> [component...]");
  console.log("Use `pnpm ui:list:nyx` to inspect the reviewed installable NyxUI subset.");
  console.log("Use `pnpm ui:validate:nyx` to validate the shadcn and Nyx registry wiring.");
}

async function readPackageManifest() {
  return JSON.parse(await readFile(packageJsonPath, "utf8"));
}

export async function main(args = process.argv.slice(2)) {
  const parsedArgs = parseCliArgs(args);

  if (parsedArgs.list) {
    console.log(formatCuratedNyxList());
    return 0;
  }

  if (parsedArgs.validate) {
    return runValidation();
  }

  const { rejected, selected } = resolveNyxComponents(parsedArgs.componentSpecifiers);

  if (rejected.length > 0) {
    console.error(`[ui:add:nyx] Unsupported NyxUI components: ${rejected.join(", ")}`);
    console.error("[ui:add:nyx] Allowed NyxUI components:");
    console.error(formatCuratedNyxList());
    return 1;
  }

  if (selected.length === 0) {
    printUsage();
    return 1;
  }

  const { nyxRegistryUrl } = await validateInstalledShadcnConfig();

  const packageManifest = await readPackageManifest();
  const missingDependencies = findMissingDependencies(selected, packageManifest);

  if (missingDependencies.length > 0) {
    console.error(
      `[ui:add:nyx] Missing required dependencies for the reviewed NyxUI subset: ${missingDependencies.join(", ")}`,
    );
    return 1;
  }

  const auditResult = await auditCuratedNyxComponents(selected, nyxRegistryUrl);

  if (auditResult.invalidComponents.length > 0) {
    console.error("[ui:add:nyx] Selected Nyx components failed metadata validation:");
    console.error(formatAuditIssues(auditResult.issuesByComponent));
    return 1;
  }

  const installTargets = selected.map(toNyxTarget);
  const operation = parsedArgs.dryRun ? "view" : "add";

  return runShadcnCommand(operation, installTargets, parsedArgs.forwardedArgs);
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  main().then(
    (exitCode) => {
      if (exitCode !== 0) {
        process.exitCode = exitCode;
      }
    },
    (error) => {
      console.error("[ui:add:nyx] Failed to install NyxUI component", error);
      process.exitCode = 1;
    },
  );
}