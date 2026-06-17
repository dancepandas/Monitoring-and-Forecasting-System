import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(null)
  const role = ref('')

  async function login(username, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || '登录失败')
    }
    const data = await res.json()
    token.value = data.token
    user.value = data.user
    role.value = data.user.role
    localStorage.setItem('token', data.token)
    return data
  }

  function logout() {
    token.value = ''
    user.value = null
    role.value = ''
    localStorage.removeItem('token')
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const res = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token.value}` }
      })
      if (res.ok) {
        const data = await res.json()
        user.value = data.user
        role.value = data.user.role
      }
    } catch {}
  }

  return { token, user, role, login, logout, fetchMe }
})
