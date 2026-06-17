import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './store/auth'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia())

const auth = useAuthStore()
if (localStorage.getItem('token')) {
  auth.fetchMe().catch(() => {})
}

app.use(router)
app.mount('#app')
