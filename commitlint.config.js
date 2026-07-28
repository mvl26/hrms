module.exports = {
	parserPreset: "conventional-changelog-conventionalcommits",
	rules: {
		"subject-empty": [2, "never"],
		"type-case": [2, "always", "lower-case"],
		"type-empty": [2, "never"],
		"type-enum": [
			2,
			"always",
			[
				"build",
				"chore",
				"ci",
				"docs",
				"feat",
				"fix",
				// Miyano: lớp bản địa hóa VN có commit chỉ đụng bản dịch (hrms/translations/vi.csv)
				"i18n",
				"perf",
				"refactor",
				"revert",
				"style",
				"test",
				"patch",
			],
		],
	},
};
