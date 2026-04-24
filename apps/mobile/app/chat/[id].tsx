import { useEffect, useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "../../src/context/AuthContext";
import { useChat, type ChatMessage } from "../../src/hooks/useChat";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <View className={`px-4 py-1 ${isUser ? "items-end" : "items-start"}`}>
      <View
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
          isUser ? "bg-brand rounded-tr-sm" : "bg-zinc-800 rounded-tl-sm"
        }`}
      >
        <Text className="text-white text-base leading-relaxed">{msg.text}</Text>
        {msg.sources && msg.sources.length > 0 && (
          <View className="mt-1.5 gap-0.5">
            {msg.sources.map((s, i) => (
              <Text key={i} className="text-indigo-300 text-xs opacity-80" numberOfLines={1}>
                ↗ {s.title ?? s.url ?? "source"}
              </Text>
            ))}
          </View>
        )}
      </View>
    </View>
  );
}

// Live typing bubble shown while streaming tokens arrive
function StreamingBubble({ text }: { text: string }) {
  return (
    <View className="px-4 py-1 items-start">
      <View className="max-w-[80%] rounded-2xl rounded-tl-sm bg-zinc-800 px-4 py-2.5">
        {text ? (
          <Text className="text-white text-base leading-relaxed">{text}</Text>
        ) : (
          <View className="flex-row gap-1 items-center py-1">
            <View className="w-2 h-2 rounded-full bg-zinc-500" />
            <View className="w-2 h-2 rounded-full bg-zinc-500 opacity-70" />
            <View className="w-2 h-2 rounded-full bg-zinc-500 opacity-40" />
          </View>
        )}
      </View>
    </View>
  );
}

export default function ChatScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { ownerId, accessToken } = useAuth();
  const [inputText, setInputText] = useState("");
  const flatListRef = useRef<FlatList>(null);

  const { messages, streamingText, connectionState, degraded, connect, disconnect, sendMessage } =
    useChat(ownerId ?? "", accessToken ?? "", id === "new" ? undefined : id);

  useEffect(() => {
    if (ownerId && accessToken) connect();
    return () => disconnect();
  }, [ownerId, accessToken]);

  // Scroll to bottom when new messages arrive or streaming text grows
  useEffect(() => {
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }, [messages.length, !!streamingText]);

  const handleSend = () => {
    if (!inputText.trim()) return;
    sendMessage(inputText);
    setInputText("");
  };

  const statusColor =
    connectionState === "connected"
      ? "#22c55e"
      : connectionState === "connecting"
      ? "#f59e0b"
      : "#ef4444";

  const isStreaming = streamingText.length > 0;

  return (
    <SafeAreaView className="flex-1 bg-black">
      {/* Header */}
      <View className="flex-row items-center px-4 py-3 border-b border-zinc-900 gap-3">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <View className="flex-1">
          <Text className="text-white font-semibold text-lg">Chat</Text>
          <View className="flex-row items-center gap-1.5">
            <View className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
            <Text className="text-zinc-500 text-xs capitalize">{connectionState}</Text>
          </View>
        </View>
        {(connectionState === "disconnected" || connectionState === "error") && (
          <Pressable onPress={connect} className="active:opacity-60">
            <Ionicons name="refresh" size={20} color="#6366f1" />
          </Pressable>
        )}
      </View>

      {/* Degraded warning */}
      {degraded && (
        <View className="bg-amber-900/40 border-b border-amber-800 px-4 py-2">
          <Text className="text-amber-300 text-xs">
            Knowledge search unavailable — responses may be less accurate.
          </Text>
        </View>
      )}

      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        className="flex-1"
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(m) => m.id}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingVertical: 12, gap: 4 }}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
          ListEmptyComponent={
            !isStreaming ? (
              <View className="items-center justify-center py-20 gap-2">
                <Ionicons name="chatbubble-outline" size={36} color="#3f3f46" />
                <Text className="text-zinc-500 text-sm">Say something to start</Text>
              </View>
            ) : null
          }
          ListFooterComponent={
            isStreaming ? <StreamingBubble text={streamingText} /> : null
          }
          renderItem={({ item }) => <MessageBubble msg={item} />}
        />

        {/* Input bar */}
        <View className="flex-row items-end gap-2 px-4 py-3 border-t border-zinc-900">
          <TextInput
            className="flex-1 bg-zinc-900 text-white rounded-2xl px-4 py-3 border border-zinc-800 max-h-28"
            placeholder="Message…"
            placeholderTextColor="#71717a"
            value={inputText}
            onChangeText={setInputText}
            multiline
            returnKeyType="send"
            onSubmitEditing={handleSend}
            blurOnSubmit={false}
            editable={connectionState === "connected" && !isStreaming}
          />
          <Pressable
            onPress={handleSend}
            disabled={!inputText.trim() || connectionState !== "connected" || isStreaming}
            className="bg-brand rounded-full w-11 h-11 items-center justify-center active:opacity-70 disabled:opacity-40"
          >
            <Ionicons name="arrow-up" size={20} color="#fff" />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
