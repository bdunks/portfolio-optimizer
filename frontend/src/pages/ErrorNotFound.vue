<template>
  <main
    class="tw:flex tw:min-h-svh tw:flex-col tw:items-center tw:justify-center tw:gap-4 tw:bg-background tw:px-4 tw:py-10 tw:text-center tw:text-foreground"
  >
    <h1 class="tw:m-0 tw:text-6xl tw:font-semibold tw:tracking-tight">404</h1>
    <h2 class="tw:m-0 tw:text-xl tw:font-medium tw:text-muted-foreground">Oops. Nothing here...</h2>
    <Button as-child>
      <RouterLink to="/">Go Home</RouterLink>
    </Button>
  </main>
</template>

<script setup lang="ts">
import { Button } from '@/components/ui/button';
import { RouterLink } from 'vue-router';
</script>
