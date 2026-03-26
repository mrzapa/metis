#!/usr/bin/env node

import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { unzipSync } from "fflate";
import { path7za } from "7zip-bin";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const brainAssetDir = path.join(appRoot, "assets-src", "brain");
const sourceBrainGlb = path.join(brainAssetDir, "brain-hologram.glb");
const sourceBrainZip = path.join(brainAssetDir, "brain-model.zip");
const sourceNeuronDir = path.join(brainAssetDir, "neurons");

const outputBrainFile = path.join(appRoot, "public", "brain", "brain-model.glb");
const outputBrainDir = path.dirname(outputBrainFile);
const outputNeuronDir = path.join(appRoot, "public", "brain", "neurons");

function fail(message) {
  console.error(`[prepare-brain-model] ${message}`);
  process.exit(1);
}

function upToDate(outputPath, sourceStat) {
  if (!existsSync(outputPath)) {
    return false;
  }

  const outputStat = statSync(outputPath);
  return outputStat.size > 0 && (!sourceStat || outputStat.mtimeMs >= sourceStat.mtimeMs);
}

function extractBrainModelZip(tempFile) {
  let archiveEntries;

  try {
    archiveEntries = unzipSync(readFileSync(sourceBrainZip));
  } catch (error) {
    fail(
      `failed to read ${path.basename(sourceBrainZip)}: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }

  const glbEntries = Object.entries(archiveEntries).filter(
    ([entryName, bytes]) => !entryName.endsWith("/") && entryName.toLowerCase().endsWith(".glb") && bytes.length > 0,
  );

  if (glbEntries.length !== 1) {
    fail(
      `archive must contain exactly one .glb entry, found ${glbEntries.length}`,
    );
  }

  writeFileSync(tempFile, Buffer.from(glbEntries[0][1]));
}

function writePreparedFile(tempPath, outputPath, sourceStat) {
  if (!existsSync(tempPath) || statSync(tempPath).size === 0) {
    fail(`preparation completed without a valid temporary output: ${path.basename(outputPath)}`);
  }

  if (existsSync(outputPath)) {
    unlinkSync(outputPath);
  }

  renameSync(tempPath, outputPath);
  if (sourceStat) {
    utimesSync(outputPath, sourceStat.atime, sourceStat.mtime);
  }
}

function prepareBrainModel() {
  mkdirSync(outputBrainDir, { recursive: true });

  if (existsSync(sourceBrainGlb)) {
    const sourceStat = statSync(sourceBrainGlb);
    if (upToDate(outputBrainFile, sourceStat)) {
      console.log(`[prepare-brain-model] Up to date: ${path.relative(appRoot, outputBrainFile)}`);
      return;
    }

    const tempFile = path.join(outputBrainDir, "brain-model.glb.tmp");
    rmSync(tempFile, { force: true });
    copyFileSync(sourceBrainGlb, tempFile);
    writePreparedFile(tempFile, outputBrainFile, sourceStat);
    console.log(`[prepare-brain-model] Prepared ${path.relative(appRoot, outputBrainFile)} from ${path.relative(appRoot, sourceBrainGlb)}`);
    return;
  }

  if (existsSync(sourceBrainZip)) {
    const sourceStat = statSync(sourceBrainZip);
    if (upToDate(outputBrainFile, sourceStat)) {
      console.log(`[prepare-brain-model] Up to date: ${path.relative(appRoot, outputBrainFile)}`);
      return;
    }

    const tempFile = path.join(outputBrainDir, "brain-model.glb.tmp");
    rmSync(tempFile, { force: true });
    extractBrainModelZip(tempFile);
    writePreparedFile(tempFile, outputBrainFile, sourceStat);
    console.log(`[prepare-brain-model] Prepared ${path.relative(appRoot, outputBrainFile)} from ${path.relative(appRoot, sourceBrainZip)}`);
    return;
  }

  if (upToDate(outputBrainFile, null)) {
    console.log(
      `[prepare-brain-model] Using existing ${path.relative(appRoot, outputBrainFile)} because no source asset was found`,
    );
    return;
  }

  fail(
    `no brain source asset found (expected one of ${path.relative(appRoot, sourceBrainGlb)} or ${path.relative(appRoot, sourceBrainZip)})`,
  );
}

function extractNeuronArchive(archivePath, outputPath, sourceStat) {
  const tempDir = mkdtempSync(path.join(os.tmpdir(), "axiom-neuron-"));
  const tempOutput = `${outputPath}.tmp`;
  rmSync(tempOutput, { force: true });

  try {
    const extractResult = spawnSync(
      path7za,
      ["e", archivePath, "-y", `-o${tempDir}`, "*.glb"],
      { encoding: "utf8" },
    );

    if (extractResult.status !== 0) {
      const details = [extractResult.stdout, extractResult.stderr]
        .filter(Boolean)
        .join("\n")
        .trim();
      fail(
        `failed to extract ${path.basename(archivePath)} with 7z${details ? `:\n${details}` : ""}`,
      );
    }

    const glbFiles = readdirSync(tempDir).filter((entry) => entry.toLowerCase().endsWith(".glb"));
    if (glbFiles.length !== 1) {
      fail(
        `archive ${path.basename(archivePath)} must contain exactly one .glb file, found ${glbFiles.length}`,
      );
    }

    copyFileSync(path.join(tempDir, glbFiles[0]), tempOutput);
    writePreparedFile(tempOutput, outputPath, sourceStat);
  } finally {
    rmSync(tempOutput, { force: true });
    rmSync(tempDir, { recursive: true, force: true });
  }
}

function prepareNeuronModels() {
  if (!existsSync(sourceNeuronDir)) {
    console.log(
      `[prepare-brain-model] Skipping neurons: source directory missing (${path.relative(appRoot, sourceNeuronDir)})`,
    );
    return;
  }

  const archives = readdirSync(sourceNeuronDir)
    .filter((entry) => entry.toLowerCase().endsWith(".7z"))
    .sort();

  if (archives.length === 0) {
    console.log("[prepare-brain-model] Skipping neurons: no .7z archives found");
    return;
  }

  mkdirSync(outputNeuronDir, { recursive: true });

  for (const archiveName of archives) {
    const archivePath = path.join(sourceNeuronDir, archiveName);
    const sourceStat = statSync(archivePath);
    const targetName = `${path.basename(archiveName, ".7z")}.glb`;
    const outputPath = path.join(outputNeuronDir, targetName);

    if (upToDate(outputPath, sourceStat)) {
      console.log(`[prepare-brain-model] Up to date: ${path.relative(appRoot, outputPath)}`);
      continue;
    }

    extractNeuronArchive(archivePath, outputPath, sourceStat);
    console.log(`[prepare-brain-model] Prepared ${path.relative(appRoot, outputPath)}`);
  }
}

function main() {
  prepareBrainModel();
  prepareNeuronModels();
}

main();
