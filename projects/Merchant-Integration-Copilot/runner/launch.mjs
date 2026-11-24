// Fixed launcher: candidate output is not a verification result.
import { pathToFileURL } from "node:url";
const module = await import(pathToFileURL(process.argv[2]).href);
const app = module.default ?? module.app;
if (!app || typeof app.listen !== "function") process.exit(2);
app.listen(8787, "127.0.0.1");
