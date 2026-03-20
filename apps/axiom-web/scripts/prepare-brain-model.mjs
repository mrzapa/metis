#!/usr/bin/env node

import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  utimesSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { unzipSync } from "fflate";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const sourceZip = path.join(appRoot, "assets-src", "brain", "brain-model.zip");
const outputFile = path.join(appRoot, "public", "brain", "brain-model.glb");
const outputDir = path.dirname(outputFile);

function fail(message) {
  console.error(`[prepare-brain-model] ${message}`);
  process.exit(1);
}

function useExistingOutput(sourceStat) {
  if (!existsSync(outputFile)) {
    return false;
  }

  const outputStat = statSync(outputFile);
  return outputStat.size > 0 && (!sourceStat || outputStat.mtimeMs >= sourceStat.mtimeMs);
}

function extractBrainModel(tempFile) {
  let archiveEntries;

  try {
    archiveEntries = unzipSync(readFileSync(sourceZip));
  } catch (error) {
    fail(
      `failed to read ${path.basename(sourceZip)}: ${
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

function main() {
  if (!existsSync(sourceZip)) {
    if (useExistingOutput(null)) {
      console.log(
        `[prepare-brain-model] Using existing ${path.relative(appRoot, outputFile)} because ${path.relative(appRoot, sourceZip)} is missing`,
      );
      return;
    }

    fail(`source archive not found at ${sourceZip}`);
  }

  const sourceStat = statSync(sourceZip);
  mkdirSync(outputDir, { recursive: true });

  if (useExistingOutput(sourceStat)) {
    console.log(`[prepare-brain-model] Up to date: ${path.relative(appRoot, outputFile)}`);
    return;
  }

  const tempFile = path.join(outputDir, "brain-model.glb.tmp");
  rmSync(tempFile, { force: true });

  extractBrainModel(tempFile);

  if (!existsSync(tempFile) || statSync(tempFile).size === 0) {
    fail("extraction completed without a valid temporary .glb output");
  }

  if (existsSync(outputFile)) {
    unlinkSync(outputFile);
  }

  renameSync(tempFile, outputFile);
  utimesSync(outputFile, sourceStat.atime, sourceStat.mtime);
  console.log(`[prepare-brain-model] Prepared ${path.relative(appRoot, outputFile)}`);
}

main();
