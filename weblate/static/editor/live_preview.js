let editor_id = 0;

function hidePreview() {
  document.querySelector("#live_preview").classList.add("hidden");
  document.querySelector("#toggle-live-preview").classList.add("hidden");
}

function setContents(el, content) {
  if (Array.isArray(content)) {
    for (const bit of content) setContents(el, bit);
    return;
  }

  if (content instanceof Node) el.appendChild(content);
  else if (content) el.appendChild(document.createTextNode(content));
}

function handleTag(key, children) {
  const el = document.createElement("span");
  el.className = "live_preview-tag";
  el.dataset.tag = key;

  setContents(el, children);
  return el;
}

function initLivePreview(root, attempt = 0) {
  if (!window.LivePreview) return;

  const preview_tab = root.querySelector("#live_preview"),
    panel = preview_tab && preview_tab.querySelector(".panel");
  if (!panel) return hidePreview();

  const editor = root.querySelector(".translation-editor");
  if (!editor) return hidePreview();

  let lang = editor.getAttribute("lang");
  const mode = preview_tab.dataset.mode;
  const parser = window.LivePreview.Parsers[mode];

  if (!parser || !lang) return hidePreview();

  // Get our tab
  const tab = root.querySelector("#toggle-live-preview"),
    badge = tab && tab.querySelector(".badge");

  // Underscores aren't valid in locales for JavaScript.
  lang = lang.replace(/_/g, "-");

  const body = panel.querySelector("div.panel-body div");
  const form = panel.querySelector("form.panel-body");

  if (!body || !form) return hidePreview();

  const variables = {};
  let editors = {},
    tags = {},
    defaults = {};
  let parsed, types, error;

  const updateTranslation = () => {
    body.innerHTML = "";

    if (error) {
      body.textContent = error;
      return;
    }

    if (!parsed) return;

    // Override defaults with user-set values.
    // Always override defaults / user-set values with tag
    // handlers if something is a tag.
    const values = Object.assign({}, defaults, variables, tags);

    let parts;
    try {
      parts = parser.interpret(parsed, lang, values);
    } catch (err) {
      body.textContent = `Interpreter Error: ${err}`;
      return;
    }

    if (parts) setContents(body, parts);
  };

  const syncContent = () => {
    const old_types = types;
    parsed = types = error = null;
    try {
      parsed = parser.parse(editor.value);
      types = parser.extract(parsed);
    } catch (err) {
      error = err.message;
    }

    const has_error = error != null;
    panel.classList.toggle("panel-default", !has_error);
    panel.classList.toggle("panel-danger", has_error);

    if (badge) {
      badge.classList.toggle("badge-danger", has_error);
      badge.textContent = has_error ? "1" : "";
    }

    const new_tags = {};
    const new_editors = {};
    const new_defaults = {};

    if (types) {
      for (const [key, type] of Object.entries(types)) {
        const old_type = old_types && old_types[key];
        if (old_type && JSON.stringify(old_type) === JSON.stringify(type)) {
          // Ensure the editor isn't garbage collected.
          if (editors[key]) new_editors[key] = editors[key];
          if (tags[key]) new_tags[key] = tags[key];
          if (defaults[key]) new_defaults[key] = defaults[key];
          continue;
        }

        // Tags are special and different.
        if (type.is_tag) {
          new_tags[key] = handleTag.bind(this, key);
          continue;
        }

        // Default Value
        let value;
        if (type.is_date) value = new Date();
        else if (type.is_number) value = 1;
        else if (type.type === "select" && Array.isArray(type.choices))
          value = type.choices[0];
        else value = key;

        new_defaults[key] = value;

        // Create the editor element.
        const edit_type = type.editor_type;
        let editor;

        // Allow editors to be disabled for certain elements.
        // We also don't allow editors for XML tags.
        if (edit_type === false) continue;

        if (edit_type === "select") {
          editor = document.createElement("select");
          if (Array.isArray(type.choices))
            for (const choice of type.choices) {
              const opt = document.createElement("option");
              opt.textContent = opt.value = choice;
              editor.appendChild(opt);
            }
        } else {
          editor = document.createElement("input");

          let etype = edit_type;
          if (etype === "datetime") etype = "datetime-local";

          editor.type = etype;
        }

        let set_value = variables[key];
        if (typeof set_value !== typeof value) {
          set_value = value;
        }

        if (type.is_date && set_value instanceof Date)
          editor.valueAsNumber = set_value.getTime();
        else editor.value = set_value;

        const updateValue = () => {
          let value;
          if (type.is_date) value = new Date(editor.valueAsNumber);
          else value = editor.value;

          variables[key] = value;
          updateTranslation();
        };

        const id = `lp-` + editor_id++;
        editor.id = id;
        editor.className = "form-control";
        editor.addEventListener("input", updateValue);

        const group = document.createElement("div");
        group.className = "form-group";

        const label = document.createElement("label");
        label.htmlFor = id;
        label.className = "col-sm-2 control-label";
        label.textContent = key;

        group.appendChild(label);
        group.appendChild(document.createTextNode(" "));

        const wrap = document.createElement("div");
        wrap.className = "col-sm-10";
        wrap.appendChild(editor);

        group.appendChild(wrap);

        new_editors[key] = group;
        form.appendChild(group);
      }
    }

    // Remove old editors.
    for (const [key, val] of Object.entries(editors)) {
      if (new_editors[key] !== val) val.remove();
    }

    editors = new_editors;
    tags = new_tags;
    defaults = new_defaults;

    window.LivePreview.state = {
      parser,
      parsed,
      error,
      types,
      editors,
      defaults,
      tags,
      variables,
      updateTranslation,
      syncContent,
    };

    updateTranslation();
  };

  editor.addEventListener("input", syncContent);
  syncContent();

  panel.classList.remove("hidden");
  const loader = preview_tab.querySelector("p");
  if (loader) loader.remove();
}

$(function () {
  initLivePreview(document);
});
