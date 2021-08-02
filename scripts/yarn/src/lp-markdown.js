const MarkdownIt = require("markdown-it");
const md = new MarkdownIt({
  html: false,
});

const LP = window.LivePreview || (window.LivePreview = {}),
  Parsers = LP.Parsers || (LP.Parsers = {});

Parsers["markdown"] = {
  parse(input, tokens) {
    return input;
  },
  interpret(input) {
    const element = document.createElement("div");
    element.innerHTML = md.render(input);
    return element;
  },
  extract() {
    return {};
  },
  wrapText: false,
};
