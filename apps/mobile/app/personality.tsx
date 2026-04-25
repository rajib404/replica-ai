import { useQuery } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { apiClient } from "../src/api/client";
import { ENDPOINTS } from "../src/api/endpoints";

interface PersonalityProfile {
  owner_name?: string;
  language?: string;
  personality_summary?: string;
  traits?: string[];
  interests?: string[];
  communication_style?: string;
  emotional_tone?: string;
  last_updated?: string;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View className="px-4 py-3.5">
      <Text className="text-zinc-500 text-xs mb-1">{label}</Text>
      <Text className="text-white text-sm">{value}</Text>
    </View>
  );
}

function Divider() {
  return <View className="h-px bg-zinc-800 ml-4" />;
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <View className="mx-4 bg-zinc-900 rounded-2xl border border-zinc-800 overflow-hidden">
      {children}
    </View>
  );
}

export default function PersonalityScreen() {
  const router = useRouter();

  const { data, isLoading, error } = useQuery<PersonalityProfile>({
    queryKey: ["personality"],
    queryFn: async () => {
      const { data } = await apiClient.get(ENDPOINTS.PERSONALITY_PROFILE);
      return data;
    },
    retry: 1,
  });

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Personality</Text>
      </View>

      {isLoading ? (
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color="#6366f1" />
        </View>
      ) : error || !data ? (
        <View className="flex-1 items-center justify-center gap-3 px-8">
          <Ionicons name="sparkles-outline" size={48} color="#3f3f46" />
          <Text className="text-zinc-400 text-center">Personality profile unavailable</Text>
          <Text className="text-zinc-600 text-sm text-center">
            The personality profile will appear here once your AI has had enough conversations to learn from.
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: 32, paddingTop: 16, gap: 16 }}>
          <Card>
            {data.owner_name && <InfoRow label="Name" value={data.owner_name} />}
            {data.owner_name && data.language && <Divider />}
            {data.language && <InfoRow label="Language" value={data.language.toUpperCase()} />}
            {data.communication_style && (
              <>
                <Divider />
                <InfoRow label="Communication style" value={data.communication_style} />
              </>
            )}
            {data.emotional_tone && (
              <>
                <Divider />
                <InfoRow label="Emotional tone" value={data.emotional_tone} />
              </>
            )}
          </Card>

          {data.personality_summary && (
            <View className="mx-4">
              <Text className="text-zinc-500 text-xs font-semibold uppercase tracking-wider mb-2 ml-1">
                Summary
              </Text>
              <View className="bg-zinc-900 rounded-2xl border border-zinc-800 px-4 py-3.5">
                <Text className="text-white text-sm leading-relaxed">{data.personality_summary}</Text>
              </View>
            </View>
          )}

          {data.traits && data.traits.length > 0 && (
            <View className="mx-4">
              <Text className="text-zinc-500 text-xs font-semibold uppercase tracking-wider mb-2 ml-1">
                Traits
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {data.traits.map((t) => (
                  <View key={t} className="bg-indigo-500/20 rounded-full px-3 py-1">
                    <Text className="text-indigo-300 text-xs">{t}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {data.interests && data.interests.length > 0 && (
            <View className="mx-4">
              <Text className="text-zinc-500 text-xs font-semibold uppercase tracking-wider mb-2 ml-1">
                Interests
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {data.interests.map((t) => (
                  <View key={t} className="bg-amber-500/20 rounded-full px-3 py-1">
                    <Text className="text-amber-300 text-xs">{t}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {data.last_updated && (
            <Text className="text-zinc-600 text-xs text-center">
              Last updated {new Date(data.last_updated).toLocaleDateString()}
            </Text>
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
