import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { Link } from "expo-router";
import { useAuth } from "../../src/context/AuthContext";
import { apiClient } from "../../src/api/client";
import { ENDPOINTS } from "../../src/api/endpoints";

export default function SetupScreen() {
  const { signIn } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [secretWord, setSecretWord] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSetup = async () => {
    if (!name.trim() || !email.trim()) {
      setError("Name and email are required.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const { data } = await apiClient.post(ENDPOINTS.AUTH_SETUP, {
        name: name.trim(),
        email: email.trim(),
        ...(secretWord.trim() ? { secret_word: secretWord.trim() } : {}),
      });
      // Response: { owner_id, tokens: { access_token, refresh_token }, ... }
      await signIn(data.tokens, data.owner_id);
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? "Setup failed. Please try again.";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      className="flex-1 bg-black"
    >
      <ScrollView
        contentContainerStyle={{ flexGrow: 1, justifyContent: "center" }}
        keyboardShouldPersistTaps="handled"
      >
        <View className="px-6 gap-6">
          <View className="gap-1">
            <Text className="text-white text-3xl font-bold">Create your replica</Text>
            <Text className="text-zinc-400 text-base">Set up your Replica AI profile</Text>
          </View>

          <View className="gap-4">
            <View className="gap-1.5">
              <Text className="text-zinc-300 text-sm font-medium">Your name</Text>
              <TextInput
                className="bg-zinc-900 text-white rounded-xl px-4 py-3.5 border border-zinc-800"
                placeholder="Alex"
                placeholderTextColor="#71717a"
                autoCapitalize="words"
                value={name}
                onChangeText={setName}
              />
            </View>

            <View className="gap-1.5">
              <Text className="text-zinc-300 text-sm font-medium">Email</Text>
              <TextInput
                className="bg-zinc-900 text-white rounded-xl px-4 py-3.5 border border-zinc-800"
                placeholder="you@example.com"
                placeholderTextColor="#71717a"
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                value={email}
                onChangeText={setEmail}
              />
            </View>

            <View className="gap-1.5">
              <Text className="text-zinc-300 text-sm font-medium">
                Secret word{" "}
                <Text className="text-zinc-500">(optional — used to verify identity)</Text>
              </Text>
              <TextInput
                className="bg-zinc-900 text-white rounded-xl px-4 py-3.5 border border-zinc-800"
                placeholder="e.g. moonlight"
                placeholderTextColor="#71717a"
                autoCapitalize="none"
                value={secretWord}
                onChangeText={setSecretWord}
              />
            </View>

            {error && <Text className="text-red-400 text-sm">{error}</Text>}

            <Pressable
              onPress={handleSetup}
              disabled={loading}
              className="bg-brand rounded-xl py-4 items-center active:opacity-80"
            >
              {loading ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text className="text-white font-semibold text-base">Create replica</Text>
              )}
            </Pressable>
          </View>

          <View className="flex-row justify-center gap-1">
            <Text className="text-zinc-400">Already have a replica?</Text>
            <Link href="/(auth)/login" className="text-brand font-medium">
              Sign in
            </Link>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
