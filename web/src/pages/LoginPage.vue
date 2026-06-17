<template>
  <div class="login-page">
    <div class="login-card">
      <h1>水文监测指挥核心</h1>
      <p>River Command Core &mdash; 请登录以继续</p>
      <div v-if="error" class="login-error">{{ error }}</div>
      <div class="login-field">
        <label for="login-username">用户名</label>
        <input id="login-username" name="username" v-model="username" type="text" placeholder="输入用户名" aria-label="用户名" @keydown.enter="handleLogin" autofocus />
      </div>
      <div class="login-field">
        <label for="login-password">密码</label>
        <input id="login-password" name="password" v-model="password" type="password" placeholder="输入密码" aria-label="密码" @keydown.enter="handleLogin" />
      </div>
      <button class="btn primary" :disabled="loading" @click="handleLogin">
        {{ loading ? '登录中...' : '登录' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    await router.replace('/')
  } catch (e) {
    error.value = e.message || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>
