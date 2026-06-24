module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  plugins: ['unused-imports'],
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-essential',
  ],
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
  },
  rules: {
    'no-unused-vars': 'off',
    'unused-imports/no-unused-imports': 'error',
    'unused-imports/no-unused-vars': ['warn', {
      vars: 'all',
      varsIgnorePattern: '^_',
      args: 'after-used',
      argsIgnorePattern: '^_',
    }],
    'vue/no-unused-vars': ['error', { ignorePattern: '^_' }],
    'vue/multi-word-component-names': 'off',
  },
};
