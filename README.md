# Text-to-Masterpiece

## Frontend structure

frontend/src/
├── assets/
│   └── 178b.png
│       # Фоновое изображение для основной страницы генерации
│
├── components/
│   ├── chat/
│   │   ├── ChatInput.tsx
│   │   │   # Переиспользуемый input для промпта:
│   │   │   # textarea, кнопка отправки, glass-стили и обработка Enter
│   │   │
│   │   ├── MessageList.tsx
│   │   │   # Отображает сообщения пользователя и ответы AI,
│   │   │   # поддерживает изображения и автоматический скролл вниз
│   │   │
│   │   └── ChatHistory.tsx
│   │       # Содержимое выдвижного sidebar:
│   │       # список предыдущих чатов пользователя
│   │
│   └── layout/
│       └── AppLayout.tsx
│           # Основной layout страницы:
│           # фон, открытие/закрытие sidebar,
│           # размещение ChatHistory и основной области приложения
│
├── pages/
│   ├── generate/
│   │   └── GeneratePage.tsx
│   │       # Основная рабочая страница генерации:
│   │       # хранит состояние сообщений и input,
│   │       # отправляет запрос на генерацию изображения
│   │       # и переключает интерфейс между hero и chat mode
│   │
│   └── home/
│       ├── home.css
│       │   # Локальные стили landing page
│       │
│       └── home.tsx
│           # Главная landing page проекта
│
├── services/
│   └── requests.ts
│       # API-клиент frontend:
│       # изолирует HTTP-запросы к FastAPI backend
│
├── App.tsx
│   # Корневой React-компонент и маршрутизация приложения
│
├── main.tsx
│   # Entry point React/Vite
│
└── styles.css
    # Главный глобальный stylesheet:
    # CSS variables, glassmorphism, cinematic background,
    # sidebar, chat history, hero block, input и сообщения
