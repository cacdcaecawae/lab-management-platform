<!-- Top of a list page (DESIGN.md): filters wrap on the left, #actions stay together at the top right. Styles in theme.css. -->
<template>
  <div class="page-toolbar">
    <div class="page-toolbar-filters"><slot /></div>
    <div v-if="$slots.actions" class="page-toolbar-actions"><slot name="actions" /></div>
  </div>
</template>
