<template>
  <code class="broker-lot-id" :aria-label="`Broker lot ID ${brokerLotId}`">{{ brokerLotId }}</code>
</template>

<script setup lang="ts">
defineProps<{ brokerLotId: string }>();
</script>

<style scoped>
.broker-lot-id {
  color: inherit;
  font: inherit;
  font-weight: 700;
}
</style>
