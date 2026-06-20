<script setup>
defineProps({
  text: { type: String, required: true },
  placement: { type: String, default: 'top' },
})
</script>

<template>
  <span class="tooltip-wrap" v-if="text">
    <span class="tip">?</span>
    <span class="tip-content">{{ text }}</span>
  </span>
</template>