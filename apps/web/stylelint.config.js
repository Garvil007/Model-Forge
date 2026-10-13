/** @type {import('stylelint').Config} */
export default {
  extends: ['stylelint-config-standard'],
  rules: {
    'custom-property-pattern': null,
    'selector-class-pattern': null,
    'color-no-hex': true,
    'declaration-property-value-disallowed-list': {
      '/^(font-size|width|height|padding|margin|gap|border-radius|top|left|right|bottom)$/': [
        /\b\d+px\b/,
      ],
    },
  },
  overrides: [
    {
      files: ['src/styles/tokens.css'],
      rules: {
        'color-no-hex': null,
        'declaration-property-value-disallowed-list': null,
      },
    },
  ],
}
