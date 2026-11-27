// Converts optolink2mqtt configuration files to the latest "config_version".
//
// Each migration edits the original text, rather than re-serializing the parsed YAML, so the
// user's comments, key order and formatting survive and the diff shows only real changes.
// The YAML library is passed in by the caller (the page loads it from a CDN, tests from npm).
//
// To support a new config_version N+1: add a function converting N to N+1 to MIGRATIONS and
// bump LATEST_VERSION, in the same PR that bumps Config.CONFIG_VERSION in config.py.

export const LATEST_VERSION = 2;

// files written before "config_version" existed are version 1
const DEFAULT_VERSION = 1;

// MIGRATIONS[n] converts a version n file into a version n+1 one
const MIGRATIONS = {
  1: v1ToV2,
};

// Returns { text, fromVersion, toVersion, notes: [{ level: "info" | "warning" | "error", message }] }.
// Throws an Error when the input is not a YAML mapping that can be upgraded.
export function upgradeConfig(text, YAML) {
  const notes = [];
  const fromVersion = readVersion(parse(text, YAML));
  if (fromVersion > LATEST_VERSION) {
    throw new Error(
      `config_version ${fromVersion} is newer than the latest version known to this tool (${LATEST_VERSION})`,
    );
  }
  for (let v = fromVersion; v < LATEST_VERSION; v++) {
    const doc = parse(text, YAML);
    const edits = [];
    MIGRATIONS[v](text, doc, YAML, edits, notes);
    setVersion(text, doc, v + 1, edits);
    text = applyEdits(text, edits);
  }
  return { text, fromVersion, toVersion: LATEST_VERSION, notes };
}

// ---------------------------------------------------------------------------
// Migrations
// ---------------------------------------------------------------------------

// Version 2 introduced the register "type" (int, float, enum, datetime_bcd), defaulting to int:
//  - a scale_factor other than 1 requires "type: float";
//  - an "enum" dictionary requires "type: enum", and a scale_factor other than 1 is no longer
//    allowed with it (version 1 ignored the scale factor of enum registers).
function v1ToV2(text, doc, YAML, edits, notes) {
  const registers = doc.contents.get("registers_poll_list", true);
  if (!YAML.isSeq(registers)) {
    return;
  }
  registers.items.forEach((reg, i) => {
    if (!YAML.isMap(reg)) {
      return;
    }
    const name = `register '${reg.get("name") ?? `#${i + 1}`}'`;
    if (reg.has("type")) {
      notes.push({ level: "info", message: `${name}: already has a "type", left unchanged` });
      return;
    }
    if (reg.has("<<")) {
      notes.push({
        level: "warning",
        message: `${name}: uses a YAML merge key ("<<"); check that the merged keys get the right "type"`,
      });
    }

    const scalePair = findPair(reg, "scale_factor", YAML);
    const scale = scalePair ? Number(scalePair.value?.value) : 1;
    let type = null;
    if (reg.has("enum")) {
      type = "enum";
      if (scale !== 1) {
        if (removePairLine(text, reg, scalePair, edits)) {
          notes.push({
            level: "info",
            message: `${name}: removed "scale_factor: ${scalePair.value.value}", which version 1 ignored for enum registers`,
          });
        } else {
          notes.push({
            level: "error",
            message: `${name}: remove "scale_factor" by hand, it is not allowed for enum registers`,
          });
        }
      }
    } else if (Number.isNaN(scale)) {
      notes.push({ level: "error", message: `${name}: "scale_factor" is not a number` });
      return;
    } else if (scale !== 1) {
      type = "float";
    }

    if (type === null) {
      return; // "type: int" is the default, nothing to add
    }
    if (insertPairAfter(text, reg, "length", `type: ${type}`, YAML, edits)) {
      notes.push({ level: "info", message: `${name}: added "type: ${type}"` });
    } else {
      notes.push({ level: "error", message: `${name}: add "type: ${type}" by hand` });
    }
  });
}

// ---------------------------------------------------------------------------
// Helpers: parsing and text edits
// ---------------------------------------------------------------------------

function parse(text, YAML) {
  // optolink2mqtt reads its config with PyYAML, which implements YAML 1.1
  const doc = YAML.parseDocument(text, { version: "1.1" });
  if (doc.errors.length > 0) {
    throw new Error(`invalid YAML: ${doc.errors[0].message}`);
  }
  if (!YAML.isMap(doc.contents) || doc.contents.flow) {
    throw new Error("the configuration must be a YAML mapping, with keys like 'optolink' and 'mqtt'");
  }
  return doc;
}

function readVersion(doc) {
  const v = doc.contents.get("config_version");
  if (v === undefined) {
    return DEFAULT_VERSION;
  }
  if (!Number.isInteger(v) || v < 1) {
    throw new Error(`invalid config_version '${v}': expected a positive integer`);
  }
  return v;
}

function setVersion(text, doc, version, edits) {
  const pair = doc.contents.items.find((p) => p.key?.value === "config_version");
  if (pair) {
    const [start, end] = pair.value.range;
    edits.push({ start, end, insert: String(version) });
  } else {
    // add it right before the first top-level key, after any header comment
    const start = lineStart(text, doc.contents.items[0].key.range[0]);
    edits.push({ start, end: start, insert: `config_version: ${version}\n\n` });
  }
}

function findPair(map, key, YAML) {
  return map.items.find((p) => YAML.isScalar(p.key) && p.key.value === key);
}

// Inserts "line" as a new key of the block mapping "map", on the line after the "afterKey" key
// (or after the last key if missing). Returns false if the mapping cannot be edited safely.
function insertPairAfter(text, map, afterKey, line, YAML, edits) {
  if (map.flow || map.items.length === 0) {
    return false;
  }
  const pair = findPair(map, afterKey, YAML) ?? map.items[map.items.length - 1];
  const keyStart = pair.key.range[0];
  const indent = keyStart - lineStart(text, keyStart);
  const valueEnd = pair.value ? pair.value.range[1] : pair.key.range[1];
  const at = lineEnd(text, valueEnd);
  edits.push({ start: at, end: at, insert: `\n${" ".repeat(indent)}${line}` });
  return true;
}

// Removes the line holding "pair", if the pair is alone on its line. Returns false otherwise.
function removePairLine(text, map, pair, edits) {
  if (map.flow) {
    return false;
  }
  const start = lineStart(text, pair.key.range[0]);
  if (text.slice(start, pair.key.range[0]).trim() !== "") {
    return false; // e.g. "- scale_factor: 2", the first key of a list item
  }
  const end = lineEnd(text, pair.value.range[1]);
  if (lineStart(text, pair.value.range[1]) !== start) {
    return false; // value spanning several lines
  }
  edits.push({ start, end: Math.min(end + 1, text.length), insert: "" });
  return true;
}

function lineStart(text, offset) {
  return text.lastIndexOf("\n", offset - 1) + 1;
}

function lineEnd(text, offset) {
  const i = text.indexOf("\n", offset);
  return i < 0 ? text.length : i;
}

function applyEdits(text, edits) {
  // apply from the end, so earlier offsets stay valid
  edits.sort((a, b) => b.start - a.start);
  for (const e of edits) {
    text = text.slice(0, e.start) + e.insert + text.slice(e.end);
  }
  return text;
}
