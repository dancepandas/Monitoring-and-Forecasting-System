<template>
  <div class="login-page">
    <div class="login-card">
      <h1>水文监测指挥核心</h1>
      <p>River Command Core &mdash; {{ isRegister ? '创建新账号' : '请登录以继续' }}</p>
      <div v-if="error" class="login-error">{{ error }}</div>

      <!-- 注册模式额外字段 -->
      <div class="login-field" v-if="isRegister">
        <label for="login-display">显示名称</label>
        <input id="login-display" v-model="displayName" type="text" placeholder="输入显示名称（可选）" @keydown.enter="handleSubmit" />
      </div>
      <div class="login-field">
        <label for="login-username">用户名</label>
        <input id="login-username" v-model="username" type="text" placeholder="输入用户名" @keydown.enter="handleSubmit" autofocus />
      </div>
      <div class="login-field">
        <label for="login-password">密码</label>
        <input id="login-password" v-model="password" type="password" placeholder="输入密码" @keydown.enter="handleSubmit" />
      </div>
      <div class="login-field" v-if="isRegister">
        <label for="login-password2">确认密码</label>
        <input id="login-password2" v-model="password2" type="password" placeholder="再次输入密码" @keydown.enter="handleSubmit" />
      </div>

      <button class="btn primary" :disabled="loading" @click="handleSubmit">
        {{ loading ? (isRegister ? '注册中...' : '登录中...') : (isRegister ? '注册' : '登录') }}
      </button>

      <p class="login-toggle">
        <a href="#" @click.prevent="toggleMode">
          {{ isRegister ? '← 已有账号？去登录' : '没有账号？注册' }}
        </a>
      </p>
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
const password2 = ref('')
const displayName = ref('')
const error = ref('')
const loading = ref(false)
const isRegister = ref(false)

function toggleMode() {
  isRegister.value = !isRegister.value
  error.value = ''
  password2.value = ''
  displayName.value = ''
}

async function handleSubmit() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  if (isRegister.value) {
    if (password.value !== password2.value) {
      error.value = '两次输入的密码不一致'
      return
    }
    if (password.value.length < 4) {
      error.value = '密码至少 4 个字符'
      return
    }
  }
  loading.value = true
  error.value = ''
  try {
    if (isRegister.value) {
      await auth.signup(username.value, password.value, displayName.value)
    } else {
      await auth.login(username.value, password.value)
    }
    await router.replace('/')
  } catch (e) {
    error.value = e.message || (isRegister.value ? '注册失败' : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
