const fmParse = require("format-message-parse");
const fmInterpret = require("format-message-interpret");

const TAG_TYPE = "<,TAG,>",
  NUMERIC_TYPES = ["number", "plural", "selectordinal", "spellout"],
  DATE_TYPES = ["date", "time", "datetime"],
  INPUT_TYPES = {
    date: "date",
    time: "time",
    datetime: "datetime-local",
    duration: "number",
    select: "select",
  };

function update_maybe_value(value, old) {
  if (old === undefined || value === old) return value;
  return null;
}

function extract(ast, variables = {}) {
  // Note: This method is similar to extract_placeholders from the icu.py
  // module but working with an AST that is formatted differently.

  if (!Array.isArray(ast)) return variables;

  for (const token of ast) {
    if (!Array.isArray(token)) continue;

    const name = token[0],
      type = token[1];

    if (name === "#") continue;

    const data = variables[name] || (variables[name] = { name });

    // We aren't as concerned about validating the string here, since
    // we have server-side checks. This is just about presenting a
    // mostly sane editor to the user.
    if (!data.type && type) data.type = type;
    // Though, for the sake of showing a complete editor if someone
    // is using a date placeholder for double duty, let's make sure
    // to expand to datetime.
    else if (
      (data.type === "date" && type === "time") ||
      (data.type === "time" && type === "date")
    )
      data.type = "datetime";

    data.is_number = update_maybe_value(
      NUMERIC_TYPES.includes(type),
      data.is_number
    );
    data.is_date = update_maybe_value(DATE_TYPES.includes(type), data.is_date);

    const is_tag = type === TAG_TYPE;
    data.is_tag = update_maybe_value(is_tag, data.is_tag);
    if (is_tag) {
      const children = token[2] && token[2].children,
        is_empty = !children || !Array.isArray(children) || !children.length;
      data.is_empty = update_maybe_value(is_empty, data.is_empty);
    }

    // When dealing with a select, collect its choices so we can
    // present a nice select element to the user.
    if (type === "select" && token[2]) {
      const choices = Object.keys(token[2]);
      if (data.choices) data.choices = data.choices.concat(choices);
      else data.choices = choices;
    }

    // Editor Type
    if (data.type && INPUT_TYPES[data.type])
      data.editor_type = INPUT_TYPES[data.type];
    else if (data.is_number) data.editor_type = "number";
    else if (data.is_date) data.editor_type = data.type;
    else if (data.is_tag && data.is_empty) data.editor_type = false;

    // Descend into sub-asts.
    for (let i = 2; i < 5; i++) {
      if (typeof token[i] === "object" && !Array.isArray(token[i]))
        for (const val of Object.values(token[i])) extract(val, variables);
    }
  }

  return variables;
}

function interpret(ast, locale, variables) {
  return fmInterpret.toParts(ast, locale, {
    [TAG_TYPE]: (input) => {
      const children = input && input[2] && input[2].children;
      return (fn, args) => {
        if (typeof fn === "function") return fn(children && children(args));
        return null;
      };
    },
  })(variables);
}

const LP = window.LivePreview || (window.LivePreview = {}),
  Parsers = LP.Parsers || (LP.Parsers = {});

Parsers["icu-message-format"] = {
  parse(input, tokens) {
    return fmParse(input, { tokens });
  },
  interpret,
  extract,
};

Parsers["icu-xml-format"] = {
  parse(input, tokens) {
    return fmParse(input, { tagsType: TAG_TYPE, tokens });
  },
  interpret,
  extract,
  _original: {
    parse: fmParse,
    interpret: fmInterpret,
  },
};
