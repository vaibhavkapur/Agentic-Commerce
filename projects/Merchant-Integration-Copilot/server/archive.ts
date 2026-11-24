import yauzl from "yauzl";
import type { SourceFiles } from "../src/types";
import { safePath, validateFiles } from "./core";

export function readArchive(buffer: Buffer): Promise<SourceFiles> {
  if (buffer.length > 2_000_000) throw new Error("ZIP archive exceeds 2 MB.");
  return new Promise((resolve, reject) => {
    yauzl.fromBuffer(
      buffer,
      { lazyEntries: true, validateEntrySizes: true },
      (error, zip) => {
        if (error || !zip)
          return reject(new Error("Unable to read ZIP archive."));
        const files: SourceFiles = Object.create(null);
        let total = 0;
        let count = 0;
        let ended = false;
        const fail = (e: Error) => {
          if (ended) return;
          ended = true;
          zip.close();
          reject(e);
        };
        zip.on("error", fail);
        zip.on("entry", (entry) => {
          try {
            if (++count > 150) throw new Error("Archive has too many entries.");
            const name = entry.fileName;
            const mode = (entry.externalFileAttributes >>> 16) & 0xf000;
            if (mode === 0xa000)
              throw new Error("Symlinks and special files are not allowed.");
            if (name.endsWith("/")) {
              safePath(name.slice(0, -1));
              zip.readEntry();
              return;
            }
            safePath(name);
            if (mode && mode !== 0x8000)
              throw new Error("Symlinks and special files are not allowed.");
            if (entry.generalPurposeBitFlag & 1)
              throw new Error("Encrypted archives are not supported.");
            if (
              entry.uncompressedSize > 256_000 ||
              total + entry.uncompressedSize > 2_000_000
            )
              throw new Error("Expanded archive exceeds source limits.");
            if (Object.hasOwn(files, name))
              throw new Error("Duplicate archive path.");
            zip.openReadStream(entry, (err, stream) => {
              if (err || !stream)
                return fail(new Error("Could not read archive entry."));
              const chunks: Buffer[] = [];
              let size = 0;
              stream.on("data", (chunk: Buffer) => {
                size += chunk.length;
                total += chunk.length;
                if (size > 256_000 || total > 2_000_000) {
                  stream.destroy();
                  fail(new Error("Expanded archive exceeds source limits."));
                } else chunks.push(chunk);
              });
              stream.on("error", fail);
              stream.on("end", () => {
                if (ended) return;
                try {
                  files[name] = new TextDecoder("utf-8", {
                    fatal: true,
                  }).decode(Buffer.concat(chunks));
                  zip.readEntry();
                } catch {
                  fail(
                    new Error("Only UTF-8 text source files are supported."),
                  );
                }
              });
            });
          } catch (e) {
            fail(e as Error);
          }
        });
        zip.on("end", () => {
          if (ended) return;
          try {
            // Permit one wrapping repository directory, but validate every original path first.
            const names = Object.keys(files);
            const prefix = names[0]?.split("/")[0] + "/";
            const normalized =
              !files["package.json"] && names.every((p) => p.startsWith(prefix))
                ? Object.fromEntries(
                    names.map((p) => [p.slice(prefix.length), files[p]]),
                  )
                : files;
            resolve(validateFiles(normalized));
            ended = true;
          } catch (e) {
            fail(e as Error);
          }
        });
        zip.readEntry();
      },
    );
  });
}
