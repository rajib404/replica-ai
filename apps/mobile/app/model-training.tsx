import { Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

function InfoCard({ icon, title, body }: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  body: string;
}) {
  return (
    <View className="bg-zinc-900 rounded-2xl border border-zinc-800 p-4 gap-2">
      <View className="flex-row items-center gap-2">
        <Ionicons name={icon} size={16} color="#8b5cf6" />
        <Text className="text-white font-semibold text-sm">{title}</Text>
      </View>
      <Text className="text-zinc-400 text-sm leading-relaxed">{body}</Text>
    </View>
  );
}

export default function ModelTrainingScreen() {
  const router = useRouter();

  return (
    <SafeAreaView className="flex-1 bg-black" edges={["top", "left", "right"]}>
      <View className="flex-row items-center gap-3 px-4 py-3 border-b border-zinc-900">
        <Pressable onPress={() => router.back()} className="active:opacity-60">
          <Ionicons name="arrow-back" size={24} color="#fff" />
        </Pressable>
        <Text className="text-white font-semibold text-lg flex-1">Model Training</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 32, gap: 16 }}>
        {/* Status banner */}
        <View className="bg-violet-500/10 border border-violet-500/30 rounded-2xl px-4 py-4 flex-row items-center gap-3">
          <Ionicons name="hardware-chip" size={24} color="#8b5cf6" />
          <View className="flex-1">
            <Text className="text-violet-300 font-semibold">Managed from the web dashboard</Text>
            <Text className="text-violet-400/70 text-sm">
              Trigger and monitor fine-tuning jobs at replica.ai/dashboard/training
            </Text>
          </View>
        </View>

        <InfoCard
          icon="information-circle"
          title="What is model training?"
          body="Model training fine-tunes your personal AI on your conversation history and knowledge base, making it sound more like you over time."
        />

        <InfoCard
          icon="time"
          title="When does it run?"
          body="Training jobs are triggered automatically by the self-learning system, or manually from the web dashboard. Jobs typically take 15–60 minutes."
        />

        <InfoCard
          icon="cloud-upload"
          title="What data is used?"
          body="Your past conversations and ingested knowledge entries are used as training data. Nothing is shared outside your personal instance."
        />
      </ScrollView>
    </SafeAreaView>
  );
}
