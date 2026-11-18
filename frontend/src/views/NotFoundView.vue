<template>
  <el-result icon="warning" title="页面不存在">
    <template #extra>
      <el-button type="primary" @click="$router.push('/')">回到工作台</el-button>
    </template>
  </el-result>
</template>
