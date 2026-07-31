<template>
	<img :src="logoUrl" alt="Miyano HR" />
</template>

<script setup lang="ts">
// Bind runtime chứ không để `src` tĩnh: Vite coi src tĩnh là asset import và
// Rollup sẽ cố phân giải lúc build, trong khi file này do Frappe phục vụ ở /assets.
const logoUrl = "/assets/hrms/images/miyano-hr-logo.png";
</script>
