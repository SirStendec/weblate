const parse = require('format-message-parse');
const interpret = require('format-message-interpret');

function extract(ast, out) {
	if ( ! out )
		out = {};

	if ( ! Array.isArray(ast) )
		return out;

	for(const part of ast) {
		if ( Array.isArray(part) ) {
			const name = part[0],
				type = part[1];
			if ( name === '#' )
				continue;

			let thing = out[name];
			if ( ! thing )
				thing = out[name] = {name};

			if ( ! thing.type && type )
				thing.type = type;

			if ( type === 'select' && part[2] ) {
				const choices = Object.keys(part[2]);
				if ( thing.choices )
					thing.choices = thing.choices.concat(choices);
				else
					thing.choices = choices;
			}

			for(let i=2; i < 5; i++) {
				if ( typeof part[i] === 'object' )
					for(const val of Object.values(part[i]))
						extract(val, out);
			}
		}
	}

	return out;
}

window.FormatMessageParser = {
	extract,
	parse,
	interpret
};
