import { StatusBar } from "expo-status-bar";
import React, { useEffect, useState } from "react";
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { API_BASE_URL, api } from "./src/api";

type Screen =
  | "login"
  | "today"
  | "routine"
  | "tasks"
  | "subjects"
  | "subjectDetail"
  | "materials"
  | "materialDetail"
  | "flashcards"
  | "review"
  | "calendar"
  | "simulations"
  | "essays"
  | "tutor"
  | "reports"
  | "settings";

const screens: { id: Screen; label: string }[] = [
  { id: "today", label: "Hoje" },
  { id: "routine", label: "Rotina" },
  { id: "tasks", label: "Pendências" },
  { id: "subjects", label: "Matérias" },
  { id: "materials", label: "Materiais" },
  { id: "flashcards", label: "Flashcards" },
  { id: "calendar", label: "Calendário" },
  { id: "simulations", label: "Simulados" },
  { id: "essays", label: "Redação" },
  { id: "tutor", label: "Tutor IA" },
  { id: "reports", label: "Relatórios" },
  { id: "settings", label: "Configurações" },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [data, setData] = useState<any>(null);
  const [message, setMessage] = useState("");

  async function login(path: "/api/login" | "/api/signup") {
    const payload = path === "/api/signup" ? { name: name || "Estudante", email, password } : { email, password };
    await api.post(path, payload);
    setScreen("today");
  }

  useEffect(() => {
    if (screen === "login") return;
    if (screen === "settings") {
      Promise.all([
        api.get("/api/settings"),
        api.get("/api/settings/ai-integrations/status").catch((error) => ({ visible: false, erro: error.message })),
      ])
        .then(([settingsData, aiStatus]) => setData({ ...settingsData, ai_integrations_status: aiStatus }))
        .catch((error) => setData({ erro: error.message }));
      return;
    }
    const paths: Record<Screen, string> = {
      login: "",
      today: "/api/dashboard/summary",
      routine: "/api/routine",
      tasks: "/api/pending-tasks",
      subjects: "/api/subjects",
      subjectDetail: "/api/subjects",
      materials: "/api/materials",
      materialDetail: "/api/materials",
      flashcards: "/api/flashcards",
      review: "/api/flashcards",
      calendar: "/api/calendar",
      simulations: "/api/simulations",
      essays: "/api/essays",
      tutor: "/api/tutor/sessions",
      reports: "/api/reports/weekly",
      settings: "/api/settings",
    };
    api.get(paths[screen]).then(setData).catch((error) => setData({ erro: error.message }));
  }, [screen]);

  async function sendTutorMessage() {
    const result = await api.post<any>("/api/tutor/chat", { mode: "organizer", message });
    setMessage("");
    setData(result);
  }

  if (screen === "login") {
    return (
      <SafeAreaView style={styles.app}>
        <StatusBar style="light" />
        <View style={styles.card}>
          <Text style={styles.logo}>AprovaOS</Text>
          <Text style={styles.muted}>Backend: {API_BASE_URL}</Text>
          <TextInput style={styles.input} placeholder="Nome" placeholderTextColor="#94a3b8" value={name} onChangeText={setName} />
          <TextInput style={styles.input} placeholder="E-mail" placeholderTextColor="#94a3b8" value={email} onChangeText={setEmail} autoCapitalize="none" />
          <TextInput style={styles.input} placeholder="Senha" placeholderTextColor="#94a3b8" value={password} onChangeText={setPassword} secureTextEntry />
          <Pressable style={styles.primary} onPress={() => login("/api/login")}><Text style={styles.buttonText}>Entrar</Text></Pressable>
          <Pressable style={styles.secondary} onPress={() => login("/api/signup")}><Text style={styles.buttonText}>Criar conta</Text></Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="light" />
      <ScrollView horizontal style={styles.tabs} contentContainerStyle={styles.tabsInner}>
        {screens.map((item) => (
          <Pressable key={item.id} style={[styles.tab, screen === item.id && styles.activeTab]} onPress={() => setScreen(item.id)}>
            <Text style={styles.tabText}>{item.label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <ScrollView style={styles.content}>
        <Text style={styles.title}>{screens.find((item) => item.id === screen)?.label}</Text>
        {screen === "tutor" && (
          <View style={styles.card}>
            <TextInput style={[styles.input, styles.textArea]} multiline placeholder="Pergunte ao Tutor IA" placeholderTextColor="#94a3b8" value={message} onChangeText={setMessage} />
            <Pressable style={styles.primary} onPress={sendTutorMessage}><Text style={styles.buttonText}>Enviar</Text></Pressable>
          </View>
        )}
        <View style={styles.card}>
          <Text style={styles.json}>{JSON.stringify(data, null, 2)}</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: "#07111f" },
  card: { backgroundColor: "#0f172a", borderColor: "#1e293b", borderRadius: 10, borderWidth: 1, gap: 12, margin: 16, padding: 16 },
  logo: { color: "#f8fafc", fontSize: 32, fontWeight: "800" },
  muted: { color: "#94a3b8" },
  input: { backgroundColor: "#111827", borderColor: "#334155", borderRadius: 8, borderWidth: 1, color: "#f8fafc", padding: 12 },
  textArea: { minHeight: 96, textAlignVertical: "top" },
  primary: { alignItems: "center", backgroundColor: "#2563eb", borderRadius: 8, padding: 12 },
  secondary: { alignItems: "center", backgroundColor: "#1e293b", borderRadius: 8, padding: 12 },
  buttonText: { color: "#f8fafc", fontWeight: "700" },
  tabs: { maxHeight: 54 },
  tabsInner: { gap: 8, padding: 10 },
  tab: { backgroundColor: "#111827", borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  activeTab: { backgroundColor: "#2563eb" },
  tabText: { color: "#e2e8f0", fontWeight: "700" },
  content: { flex: 1 },
  title: { color: "#f8fafc", fontSize: 24, fontWeight: "800", marginHorizontal: 16, marginTop: 16 },
  json: { color: "#cbd5e1", fontFamily: "monospace" },
});
