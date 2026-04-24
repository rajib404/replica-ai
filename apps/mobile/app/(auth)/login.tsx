import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { Link } from "expo-router";
import { useAuth } from "../../src/context/AuthContext";
import { apiClient } from "../../src/api/client";
import { ENDPOINTS } from "../../src/api/endpoints";
import { getOwnerId } from "../../src/store/auth";

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [ownerId, setOwnerIdInput] = useState("");
  const [secretWord, setSecretWord] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleVerify = async () => {
    const id = ownerId.trim() || (await getOwnerId()) || "";
    if (!id) {
      setError("Owner ID is required. Check your welcome email or web dashboard.");
      return;
    }
    if (!secretWord.trim()) {
      setError("Please enter your secret word.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const { data } = await apiClient.post(ENDPOINTS.AUTH_VERIFY, {
        owner_id: id,
        verification_type: "secret_word",
        value: secretWord.trim(),
      });
      if (!data.verified || !data.tokens) {
        setError(data.message ?? "Verification failed.");
        return;
      }
      await signIn(data.tokens, id);
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? "Sign in failed. Please try again.";
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
      <View className="flex-1 justify-center px-6 gap-6">
        <View className="gap-1">
          <Text className="text-white text-3xl font-bold">Welcome back</Text>
          <Text className="text-zinc-400 text-base">Verify your identity to continue</Text>
        </View>

        <View className="gap-4">
          <View className="gap-1.5">
            <Text className="text-zinc-300 text-sm font-medium">Owner ID</Text>
            <TextInput
              className="bg-zinc-900 text-white rounded-xl px-4 py-3.5 border border-zinc-800"
              placeholder="Paste your owner ID"
              placeholderTextColor="#71717a"
              autoCapitalize="none"
              autoCorrect={false}
              value={ownerId}
              onChangeText={setOwnerIdInput}
            />
            <Text className="text-zinc-600 text-xs">
              Find this in your web dashboard or welcome email.
            </Text>
          </View>

          <View className="gap-1.5">
            <Text className="text-zinc-300 text-sm font-medium">Secret word</Text>
            <TextInput
              className="bg-zinc-900 text-white rounded-xl px-4 py-3.5 border border-zinc-800"
              placeholder="Your secret word"
              placeholderTextColor="#71717a"
              autoCapitalize="none"
              secureTextEntry
              value={secretWord}
              onChangeText={setSecretWord}
            />
          </View>

          {error && <Text className="text-red-400 text-sm">{error}</Text>}

          <Pressable
            onPress={handleVerify}
            disabled={loading}
            className="bg-brand rounded-xl py-4 items-center active:opacity-80"
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text className="text-white font-semibold text-base">Verify & sign in</Text>
            )}
          </Pressable>
        </View>

        <View className="flex-row justify-center gap-1">
          <Text className="text-zinc-400">New here?</Text>
          <Link href="/(auth)/setup" className="text-brand font-medium">
            Create a replica
          </Link>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
