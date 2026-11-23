<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { postAuthTarget } from '@/router/post-auth'
import icon from '@/assets/phase-icon.png'
import GlassRing from './home/GlassRing.vue'
import HomeApps from './home/HomeApps.vue'
import HomeFiles from './home/HomeFiles.vue'

// The home page (DESIGN.md "首页"): what Phase is, and 登录 opening the sign-in sheet. Sent here from a page (the
// session ended, a link in a notice or an email), the sheet opens straight away and signing in goes back there.
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const next = postAuthTarget(router, route.query.next)
const form = reactive({ username: '', password: '' })
const error = ref('')
const loading = ref(false)
const sheet = ref<HTMLDialogElement>()
const enter = ref<HTMLButtonElement>()
const scrolled = ref(false) // the big 登录 has scrolled away: the bar offers one
// Signed in (the sidebar's Phase leads here): the button goes in instead of opening the sheet; ops has only 系统管理.
const enterLabel = computed(() => (!auth.user ? '登录' : auth.user.group ? '进入工作台' : '进入系统管理'))
const enterOrSignIn = () => (auth.user ? void router.push({ name: 'workbench' }) : sheet.value?.showModal())

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    await router.replace(next ?? { name: 'workbench' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

// The sheet's content fills the dialog box, so a click lands on the dialog itself only on the blurred page around it.
function outside(e: MouseEvent) {
  if (e.target === sheet.value) sheet.value.close()
}

let bar: IntersectionObserver | undefined
onMounted(() => {
  bar = new IntersectionObserver(([e]) => (scrolled.value = !e.isIntersecting))
  bar.observe(enter.value!)
  if (next) sheet.value!.showModal()
})
onBeforeUnmount(() => bar?.disconnect())
</script>

<template>
  <div class="home">
    <header class="top" :class="{ scrolled }">
      <span class="brand"><img :src="icon" alt="" />Phase</span>
      <!-- inert while hidden: neither focus nor a screen reader should find a second, invisible 登录 -->
      <button class="dark" type="button" :inert="!scrolled" @click="enterOrSignIn">{{ enterLabel }}</button>
    </header>

    <main>
      <section class="hero">
        <GlassRing />
        <h1>Phase</h1>
        <button ref="enter" class="dark" type="button" @click="enterOrSignIn">{{ enterLabel }}</button>
        <p class="say">科研资料存得住，<br />课题组日常管得清。</p>
      </section>

      <section class="cards">
        <article class="intro">
          <div class="pic"><HomeFiles /></div>
          <h2>科研资料原样留存，每一步都可追溯</h2>
          <p>
            把实验记录和原始数据放在一起，留下处理程序和结果。知识库文档保留每次上传的版本。配置每日加密备份后，数据库和附件都可以从备份恢复。
          </p>
        </article>
        <article class="intro">
          <div class="pic"><HomeApps /></div>
          <h2>课题组的日常事务，一个平台管清楚</h2>
          <p>
            项目进展、设备预约、耗材和试样、周报与组会、采购与报销，都在这里办。个人的记录只有本人、导师和管理员看得到。电脑和手机上都能用。
          </p>
        </article>
      </section>
    </main>

    <footer>Phase · 仅限课题组成员使用</footer>

    <!-- native dialog: Esc, keeping focus inside and the blurred backdrop come with it -->
    <dialog ref="sheet" aria-labelledby="login-title" @click="outside">
      <div class="sheet">
        <button class="x" type="button" aria-label="关闭" @click="sheet?.close()">
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M1.5 1.5l9 9M10.5 1.5l-9 9" /></svg>
        </button>
        <img :src="icon" alt="" />
        <h2 id="login-title">登录 Phase</h2>
        <form @submit.prevent="submit">
          <div class="field">
            <input id="login-user" v-model="form.username" placeholder=" " autocomplete="username" required autofocus />
            <label for="login-user">学号 / 工号</label>
          </div>
          <div class="field">
            <input id="login-pass" v-model="form.password" type="password" placeholder=" " autocomplete="current-password" required />
            <label for="login-pass">密码</label>
          </div>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <button class="dark" type="submit" :disabled="loading">{{ loading ? '正在登录…' : '登录' }}</button>
        </form>
        <p class="note">还没有账号？打开课题组管理员发的注册链接申请。</p>
      </div>
    </dialog>
  </div>
</template>

<!-- Sizes, the white page and the shadows are this page's own (DESIGN.md "首页"); text colours come from the theme. -->
<style scoped>
.home {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #fff;
  color: var(--lab-text);
  font-size: 17px;
  line-height: 1.6;
}
main {
  flex: 1;
}

/* one bar, one name */
.top {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 48px;
  padding: 0 22px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: saturate(1.8) blur(20px);
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.brand img {
  width: 24px;
  height: 24px;
}
.top .dark {
  min-width: 0;
  height: 30px;
  padding: 0 16px;
  font-size: 14px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.25s;
}
.top.scrolled .dark {
  opacity: 1;
  pointer-events: auto;
}

.dark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 146px;
  height: 44px;
  padding: 0 28px;
  border: 0;
  border-radius: 22px;
  background: var(--lab-text);
  color: #fff;
  font-family: inherit;
  font-size: 17px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.dark:hover {
  background: #000;
}
.dark:disabled {
  opacity: 0.6;
  cursor: default;
}
.dark:focus-visible,
.x:focus-visible {
  outline: 3px solid rgba(0, 113, 227, 0.45);
  outline-offset: 2px;
}

/* hero: picture, name, one button, one sentence */
.hero {
  padding: 6px 24px 0;
  text-align: center;
}
h1 {
  margin: -4px 0 0;
  font-size: clamp(76px, 11.4vw, 156px);
  font-weight: 700;
  line-height: 1.06;
  letter-spacing: -0.035em;
}
.hero .dark {
  margin-top: 34px;
}
.say {
  margin: 46px auto 0;
  font-size: clamp(22px, 2.55vw, 36px);
  font-weight: 600;
  line-height: 1.28;
  text-wrap: balance;
}

/* two cards: a picture, a heading, a paragraph */
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 50px;
  max-width: 1430px;
  margin: 0 auto;
  padding: 118px 40px 130px;
  box-sizing: border-box;
}
.intro { /* not .card: theme.css spaces consecutive .card blocks */
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 545px;
  padding: 40px 40px 44px;
  box-sizing: border-box;
  border-radius: 22px;
  background: #fff;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.09), 0 2px 10px rgba(0, 0, 0, 0.03);
}
.pic {
  display: grid;
  place-items: center;
  height: 262px;
}
.intro h2 {
  margin: 22px 0 0;
  font-size: 26px;
  font-weight: 600;
  line-height: 1.3;
  text-wrap: balance;
}
.intro p {
  margin: auto 0 0;
  padding-top: 36px;
  font-size: 16px;
  line-height: 1.7;
  text-wrap: pretty;
}

footer {
  padding: 18px 24px 30px;
  border-top: 1px solid #e8e8ed;
  background: #f5f5f7;
  color: var(--lab-text-3);
  font-size: 12px;
  text-align: center;
}

/* sign in */
dialog {
  width: min(400px, calc(100vw - 32px));
  padding: 0;
  border: 0;
  border-radius: 22px;
  color: var(--lab-text);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.22), 0 0 0 0.5px rgba(0, 0, 0, 0.08);
}
dialog::backdrop {
  background: rgba(255, 255, 255, 0.62);
  backdrop-filter: blur(22px) saturate(1.4);
}
dialog[open] {
  animation: rise 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.98);
  }
}
.sheet {
  position: relative;
  padding: 44px 40px 36px;
  text-align: center;
}
.sheet > img {
  width: 52px;
  height: 52px;
}
.sheet h2 {
  margin: 10px 0 26px;
  font-size: 26px;
  font-weight: 600;
}
.x {
  position: absolute;
  top: 14px;
  right: 14px;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #f0f0f3;
  color: var(--lab-text-3);
  cursor: pointer;
}
.x:hover {
  background: #e6e6ea;
}
.x svg {
  width: 12px;
  height: 12px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
}
.field {
  position: relative;
  margin-bottom: 12px;
  text-align: left;
}
.field input {
  width: 100%;
  height: 52px;
  padding: 20px 16px 4px;
  box-sizing: border-box;
  border: 1px solid #d2d2d7;
  border-radius: 12px;
  outline: none;
  color: inherit;
  font: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.field label {
  position: absolute;
  top: 14px;
  left: 17px;
  color: var(--lab-text-3);
  pointer-events: none;
  transition: top 0.15s, font-size 0.15s;
}
.field input:focus {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.14);
}
.field input:focus + label,
.field input:not(:placeholder-shown) + label {
  top: 6px;
  font-size: 12px;
}
.error {
  margin: 0 0 4px;
  color: var(--el-color-danger);
  font-size: 14px;
  text-align: left;
}
.sheet .dark {
  width: 100%;
  height: 50px;
  margin-top: 10px;
  border-radius: 25px;
}
.note {
  margin: 18px 0 0;
  color: var(--lab-text-3);
  font-size: 13px;
}

@media (max-width: 980px) {
  .cards {
    grid-template-columns: 1fr;
    gap: 28px;
    max-width: 680px;
    padding: 80px 20px 90px;
  }
  .intro {
    min-height: 0;
    padding: 32px 28px 34px;
  }
  .intro p {
    padding-top: 28px;
  }
}
@media (max-width: 480px) {
  .pic {
    height: 212px;
  }
  .intro h2 {
    font-size: 22px;
  }
  .say {
    margin-top: 36px;
  }
}
@media (prefers-reduced-motion: reduce) {
  dialog[open] {
    animation: none;
  }
}
</style>
