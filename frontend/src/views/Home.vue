<template>
  <div class="flex flex-col h-screen bg-gray-50">
    <Header />
    
    <div class="flex-1 overflow-hidden flex flex-col">
      <!-- Welcome Section (when no messages) -->
      <div v-if="messages.length === 0" class="flex-1 flex items-center justify-center p-4">
        <div class="text-center max-w-2xl">
          <div class="w-20 h-20 bg-gradient-to-br from-amber-500 to-red-600 rounded-3xl flex items-center justify-center mx-auto mb-6">
            <svg class="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 class="text-3xl font-bold text-gray-900 mb-3">历史知识问答</h2>
          <p class="text-gray-500 mb-8 text-lg">探索历史长河，输入任何问题开始历史之旅</p>
          
          <!-- Recommended Questions -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl mx-auto">
            <button
              v-for="q in recommendedQuestions"
              :key="q"
              @click="sendMessage(q)"
              class="p-4 bg-white rounded-xl border border-gray-200 hover:border-amber-300 hover:shadow-md transition-all text-left text-sm text-gray-700 hover:text-amber-600"
            >
              <svg class="w-4 h-4 text-amber-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {{ q }}
            </button>
          </div>
        </div>
      </div>

      <!-- Chat Messages -->
      <div v-else ref="chatContainer" class="flex-1 overflow-y-auto p-4 space-y-4">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="flex"
          :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
        >
          <!-- Assistant Avatar -->
          <div v-if="msg.role === 'assistant'" class="flex-shrink-0 mr-3">
            <div class="w-8 h-8 bg-gradient-to-br from-amber-500 to-red-600 rounded-full flex items-center justify-center">
              <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>

          <!-- Message Bubble -->
          <div
            class="max-w-[70%] px-4 py-3"
            :class="msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'"
          >
            <div class="whitespace-pre-wrap">{{ msg.content }}</div>
            
            <!-- Entities -->
            <div v-if="msg.entities && msg.entities.length > 0" class="mt-3 pt-3 border-t border-gray-200/50">
              <div class="text-xs text-gray-500 mb-1">识别到的实体：</div>
              <div class="flex flex-wrap gap-1">
                <span v-for="entity in msg.entities" :key="entity" class="entity-tag">
                  {{ entity }}
                </span>
              </div>
            </div>
          </div>

          <!-- User Avatar -->
          <div v-if="msg.role === 'user'" class="flex-shrink-0 ml-3">
            <div class="w-8 h-8 bg-amber-100 rounded-full flex items-center justify-center">
              <span class="text-sm font-medium text-amber-700">
                {{ authStore.user?.username?.charAt(0).toUpperCase() }}
              </span>
            </div>
          </div>
        </div>

        <!-- Loading Indicator -->
        <div v-if="loading" class="flex justify-start">
          <div class="flex-shrink-0 mr-3">
            <div class="w-8 h-8 bg-gradient-to-br from-amber-500 to-red-600 rounded-full flex items-center justify-center">
              <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
          </div>
          <div class="bubble-assistant px-4 py-3">
            <div class="flex space-x-2">
              <div class="w-2 h-2 bg-gray-400 rounded-full bounce-dot" />
              <div class="w-2 h-2 bg-gray-400 rounded-full bounce-dot" />
              <div class="w-2 h-2 bg-gray-400 rounded-full bounce-dot" />
            </div>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="border-t border-gray-200 bg-white p-4">
        <form @submit.prevent="sendMessage(inputText)" class="flex space-x-3 max-w-4xl mx-auto">
          <input
            v-model="inputText"
            type="text"
            placeholder="输入您的历史问题..."
            :disabled="loading"
            class="flex-1 px-4 py-3 border border-gray-200 rounded-xl focus:border-amber-500 disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            :disabled="!inputText.trim() || loading"
            class="bg-gradient-to-r from-amber-500 to-red-600 text-white px-6 py-3 rounded-xl font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center hover:from-amber-600 hover:to-red-700 transition-all"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { qaApi } from '@/api/qa'
import type { ChatMessage } from '@/types'
import Header from '@/components/Header.vue'

const authStore = useAuthStore()
const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const loading = ref(false)
const chatContainer = ref<HTMLElement>()

const recommendedQuestions = [
  '秦始皇是谁？',
  '丝绸之路是什么时候开辟的？',
  '唐朝有哪些著名诗人？',
  '长城是什么时候修建的？'
]

async function sendMessage(text: string) {
  if (!text.trim() || loading.value) return
  
  const question = text.trim()
  inputText.value = ''
  
  // Add user message
  messages.value.push({
    role: 'user',
    content: question,
    timestamp: Date.now()
  })
  
  // Scroll to bottom
  await nextTick()
  scrollToBottom()
  
  // Send to API
  loading.value = true
  try {
    const result = await qaApi.ask({ question })
    messages.value.push({
      role: 'assistant',
      content: result.answer,
      entities: result.entities,
      timestamp: Date.now()
    })
  } catch (e: any) {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，处理您的问题时出现了错误，请稍后重试。',
      timestamp: Date.now()
    })
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

onMounted(() => {
  // Focus input on mount
  const input = document.querySelector('input[type="text"]') as HTMLInputElement
  input?.focus()
})
</script>
