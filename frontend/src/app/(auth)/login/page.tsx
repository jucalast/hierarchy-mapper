"use client";

import { useRouter } from 'next/navigation';
import LoginView from '@/components/layout/LoginView';

export default function LoginPage() {
  const router = useRouter();

  return <LoginView onLoginSuccess={() => router.push('/')} />;
}
